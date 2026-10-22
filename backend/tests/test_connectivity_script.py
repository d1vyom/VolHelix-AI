"""Read-only connectivity script behavior against a controlled HTTP boundary."""
from scripts import test_mcp_connection as script


def test_connectivity_only_reads_public_endpoints_without_credentials(monkeypatch,capsys):
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return {'serverTime':123} if url.endswith('/time') else {'symbol':'SOLUSDT','price':'150'}
        return Response()
    monkeypatch.setenv('BINANCE_API_KEY','private-do-not-print')
    assert script.check_connection('spot','SOLUSDT',get=get)==0
    assert len(calls)==2 and all(url.startswith('https://api.binance.com/api/v3/') for url,_ in calls)
    assert all('headers' not in kwargs for _,kwargs in calls)
    assert 'private' not in capsys.readouterr().out
