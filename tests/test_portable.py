from pathlib import Path
from app import config


def test_default_model_uses_bundled_model_without_user_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.delenv('ASR_MODEL_PATH', raising=False)
    model = tmp_path / 'resources' / 'models' / 'faster-whisper-small'
    model.mkdir(parents=True)
    (model / 'model.bin').write_bytes(b'model')
    settings = config.Settings.from_env()
    assert settings.asr_model == str(model)
    assert settings.asr_ready()


def test_explicit_model_path_remains_supported(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setenv('ASR_MODEL_PATH', str(tmp_path / 'custom'))
    assert config.Settings.from_env().asr_model == str(tmp_path / 'custom')
