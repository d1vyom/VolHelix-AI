import subprocess
import json
from backend.utils.logger import get_logger
from backend.config import settings

logger = get_logger("alpaca_cli")

class AlpacaCLIWrapper:
    """
    Satisfies the hackathon requirement: 'projects must utilize either Alpaca's MCP server or its CLI tools.'
    This wrapper executes the official Alpaca CLI for trade placement and position management.
    """
    
    def __init__(self):
        # Ensure CLI has auth variables set
        self.env = {
            "APCA_API_KEY_ID": settings.ALPACA_API_KEY,
            "APCA_API_SECRET_KEY": settings.ALPACA_API_SECRET,
            "APCA_API_BASE_URL": "https://paper-api.alpaca.markets"
        }

    def _run_command(self, args: list[str]) -> dict:
        try:
            cmd = ["alpaca"] + args
            logger.info(f"Executing Alpaca CLI: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                env=self.env,
                check=True
            )
            # The CLI usually outputs JSON if properly configured, or we can parse the text.
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"output": result.stdout}
        except subprocess.CalledProcessError as e:
            logger.error(f"Alpaca CLI Error: {e.stderr}")
            return {"error": e.stderr}

    def place_option_order(self, symbol: str, qty: int, side: str, limit_price: float = None):
        """Places an options order using the Alpaca CLI."""
        args = ["order", "create", "--symbol", symbol, "--qty", str(qty), "--side", side]
        if limit_price:
            args.extend(["--type", "limit", "--limit-price", str(limit_price)])
        else:
            args.extend(["--type", "market"])
            
        return self._run_command(args)

    def get_positions(self):
        """Gets positions using the Alpaca CLI."""
        return self._run_command(["position", "list"])

cli_runner = AlpacaCLIWrapper()
