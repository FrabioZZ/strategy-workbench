"""Application-level availability of the embedded replay service."""
from app.config import Settings
from app.main import create_app


def test_embedded_replay_is_available_through_workbench_application(tmp_path):
    application = create_app(Settings(data_dir=tmp_path))
    paths = application.openapi()['paths']
    prefix = '/api/trading/external-paper'
    assert f'{prefix}/capabilities' in paths
    assert 'post' in paths[f'{prefix}/sessions']
    for action in ('step', 'run', 'pause'):
        assert 'post' in paths[f'{prefix}/sessions/{{ident}}/{action}']
    # The existing workflows remain reachable in the same local application.
    assert '/api/trading/paper/sessions' in paths
    assert '/api/documents' in paths
