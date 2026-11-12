from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from app.ai.configuration import ConfigInput, is_loopback
from app.ai.client import complete
from app.ai.completion import TermAnswer, complete_mapping
from app.ai.mapping import map_strategy
from app.models import StrictModel
from app.trading.portfolios import candidates


class MappingRevision(StrictModel):
    source_revision: int = Field(ge=1, strict=True)


class MappingAnswers(MappingRevision):
    answers: list[TermAnswer] = Field(min_length=1, max_length=100)
    mapping_version: str | None = Field(default=None, min_length=1, max_length=80)


def check_cached_answers(cached, answers):
    if not answers:
        return
    decisions = cached.get('decisions', [])
    expected = {item['question_id']: (item['option_id'], item['values'] if item['option_id'] == 'custom' else {})
                for item in decisions}
    provided = {item['question_id']: (item['option_id'], item['values']) for item in answers}
    if len(provided) != len(answers) or expected != provided:
        detail = ('映射版本或所选定义已变化，请重新加载后改选。' if cached.get('mapping_version')
                  else '此草案已保存另一组术语定义，请重新生成草案后再确认。')
        raise HTTPException(409, detail)


def require_local(request: Request):
    if not request.client or not is_loopback(request.client.host):
        raise HTTPException(403,'AI 设置及调用仅允许本机回环客户端操作。')


def router(configuration, source_store):
    api=APIRouter(prefix='/api/ai',dependencies=[Depends(require_local)])

    def find_source(source_id, body):
        source = next((s for s in candidates(source_store) if s['id'] == source_id), None)
        if not source:
            raise HTTPException(404, '策略草案不存在')
        if source['stale']:
            raise HTTPException(409, '策略草案已过期，请重新提取后映射。')
        if body and body.source_revision != source['revision']:
            raise HTTPException(409, '原文版本已变化，请重新生成执行参数。')
        return source

    def current_mapping(source_id, result=None, expected_version=None):
        try:
            if expected_version is not None:
                return source_store.current_ai_mapping(source_id, result, expected_version=expected_version)
            return source_store.current_ai_mapping(source_id, result)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    def mapping_response(source, result, config):
        use_model = result.get('resolution_method') == 'ai' or not result.get('term_version')
        response = dict(
            source_id=source['id'], source_revision=source['revision'], timeframe='daily',
            provider=config.ai_provider if use_model else '本地术语库',
            model=config.ai_model if use_model else result['term_version'], **result,
        )
        cited_segments = (source['corrected_transcript'] if source['evidence_transcript_version'] == 'corrected'
                          else source['transcript'])
        by_id = {segment['id']: segment for segment in cited_segments or []}
        for ref in response['evidence']:
            segment = by_id[ref['segment_id']]
            ref.update(start=segment.get('start'), end=segment.get('end'))
        return response

    @api.get('/config')
    def get_config(): return configuration.public()

    @api.put('/config')
    def save_config(body: ConfigInput):
        try: return configuration.save(body)
        except ValueError as exc: raise HTTPException(400,str(exc)) from None

    @api.delete('/config')
    def delete_config(): return configuration.delete()

    @api.post('/test')
    def test():
        try:
            complete(configuration.current(),[{'role':'user','content':'Reply with OK only.'}],probe=True)
            return {'ok':True,'message':'已收到所选模型的有效回复；此测试不保证提取质量。'}
        except ValueError as exc:
            return {'ok':False,'message':str(exc)}

    @api.post('/strategies/{source_id}/mapping')
    def mapping(source_id: str, body: MappingAnswers | None = None):
        source = find_source(source_id, body)
        answers = [answer.model_dump() for answer in body.answers] if body else []
        expected = body.mapping_version if body else None
        cached = current_mapping(source_id)
        if expected is not None:
            if not cached or cached.get('mapping_version') != expected:
                if cached and cached.get('replaces_mapping_version') == expected:
                    check_cached_answers(cached, answers)
                    return cached
                raise HTTPException(409, '映射版本已变化，请重新加载后确认。')
        elif cached is not None:
            check_cached_answers(cached, answers)
            return cached

        try:
            config = configuration.current()
            result = map_strategy(config, source, answers)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if expected is not None and result['ready']:
            result.update(mapping_version=uuid4().hex, resolution_method='manual',
                          replaces_mapping_version=expected, clarifications=cached['clarifications'])
            result['evidence'].extend(ref for ref in cached['evidence'] if ref['field'] == 'asset')
        response = mapping_response(source, result, config)
        if expected is not None:
            if result['ready']:
                try:
                    return current_mapping(source_id, response, expected)
                except HTTPException:
                    current = current_mapping(source_id)
                    if not current or current.get('replaces_mapping_version') != expected:
                        raise
                    check_cached_answers(current, answers)
                    return current
            current = current_mapping(source_id)
            if not current or current.get('mapping_version') != expected:
                raise HTTPException(409, '映射版本已变化，请重新加载后确认。')
            return response
        saved = current_mapping(source_id, response if result['ready'] else None)
        if saved is not None:
            check_cached_answers(saved, answers)
        return saved or response

    @api.post('/strategies/{source_id}/mapping/complete')
    def complete_execution(source_id: str, body: MappingRevision):
        source = find_source(source_id, body)
        cached = current_mapping(source_id)
        if cached is not None:
            return cached
        try:
            config = configuration.current()
            result = complete_mapping(config, source)
        except ValueError as exc:
            current_mapping(source_id)
            raise HTTPException(400, str(exc)) from None
        if result['ready']:
            result['mapping_version'] = uuid4().hex
        response = mapping_response(source, result, config)
        return current_mapping(source_id, response if result['ready'] else None) or response

    return api
