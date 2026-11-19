"""BSE connector: bhavcopy fallback parsing and honest failure."""
from data.connectors.bse_connector import BSEConnector

BHAVCOPY_SAMPLE = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric\n"
    "20251114,20251114,CM,0,STK,1,INE669E01016,IDEA,A,,,,,VODAFONE IDEA  LIMITED,30,31,29,30.5\n"
    "20251114,20251114,CM,0,STK,2,INE117A01022,ABB,A,,,,,ABB INDIA LIMITED,5000,5100,4950,5050\n"
    "20251114,20251114,CM,0,ETF,3,INE000X00003,SOMEETF,A,,,,,AN ETF,10,10,10,10\n"
)


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_bhavcopy_fallback_parses_stk_rows(monkeypatch):
    monkeypatch.setenv("BSE_EQUITY_MASTER_URL", "https://invalid.invalid/master.csv")

    def fake_get(url, headers=None, timeout=None):
        if "master.csv" in url:
            return _Resp(200, "<html>block page</html>")
        if "BhavCopy_BSE" in url:
            return _Resp(200, BHAVCOPY_SAMPLE)
        return _Resp(404, "")

    monkeypatch.setattr("data.connectors.bse_connector.requests.get", fake_get)
    connector = BSEConnector()
    result = connector.get_equity_master()
    assert result.ok
    symbols = {row["symbol"] for row in result.data}
    assert symbols == {"IDEA", "ABB"}  # ETF row excluded, HTML master rejected
    idea = next(row for row in result.data if row["symbol"] == "IDEA")
    assert idea["isin"] == "INE669E01016"
    assert "VODAFONE" in idea["name"]


def test_bhavcopy_fallback_fails_honestly(monkeypatch):
    monkeypatch.setenv("BSE_EQUITY_MASTER_URL", "https://invalid.invalid/master.csv")
    monkeypatch.setattr(
        "data.connectors.bse_connector.requests.get",
        lambda url, headers=None, timeout=None: _Resp(404, "<html>nope</html>"),
    )
    connector = BSEConnector()
    result = connector.get_equity_master()
    assert not result.ok
    assert "BSE universe unavailable" in result.error
