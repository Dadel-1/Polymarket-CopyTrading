import logging
from config import CHAIN_ID, PRIVATE_KEY, RELAYER_URL, BUILDER_API_KEY, BUILDER_SECRET, BUILDER_PASS_PHRASE
from eth_utils import to_checksum_address
from abi.CTF_abi import CTF_ABI
from web3 import Web3

from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.models import OperationType, SafeTransaction
from py_builder_signing_sdk.config import BuilderConfig, BuilderApiKeyCreds

logger = logging.getLogger(__name__)

class BlockchainClient:
    """Client for interacting with the blockchain via a relayer"""
    def __init__(self):
        self.USDCe = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        self.CTF = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"
        self.CTFExchange = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982"

        # bytes32 zero for parent collection id
        self.parent_collection_id = "0x" + "00" * 32
        self.partition = [1, 2]

        builder_config = BuilderConfig(
            local_builder_creds=BuilderApiKeyCreds(
                key=BUILDER_API_KEY,
                secret=BUILDER_SECRET,
                passphrase=BUILDER_PASS_PHRASE,
            )
        )

        self.client = RelayClient(RELAYER_URL, CHAIN_ID, PRIVATE_KEY, builder_config)
        self.CTF_contract = Web3().eth.contract(address=to_checksum_address(self.CTF), abi=CTF_ABI)

    def _to_safe_transaction(self, data: str) -> SafeTransaction:
        return SafeTransaction(
            to = self.CTF,
            operation = OperationType.Call,
            data = data,
            value = "0"
        )

    def split(self, condition_id: str, amount: float) -> tuple[SafeTransaction, str]:
        usdc_amount = int(amount * 10 ** 6)  # USDCe has 6 decimals
        split_tx = self._to_safe_transaction(
            self.CTF_contract.encode_abi(
                "splitPosition",
                [self.USDCe, self.parent_collection_id, condition_id, self.partition, usdc_amount]
            )
        )
        return split_tx, "Split"

    def merge(self, condition_id: str, amount: float) -> tuple[SafeTransaction, str]:
        usdc_amount = int(amount * 10 ** 6)  # USDCe has 6 decimals
        merge_tx = self._to_safe_transaction(
            self.CTF_contract.encode_abi(
                "mergePositions",
                [self.USDCe, self.parent_collection_id, condition_id, self.partition, usdc_amount]
            )
        )
        return merge_tx, "Merge"

    def redeem(self, condition_id: str) -> tuple[SafeTransaction, str]:
        redeem_tx = self._to_safe_transaction(
            self.CTF_contract.encode_abi(
                "redeemPositions",
                [self.USDCe, self.parent_collection_id, condition_id, self.partition]
            )
        )
        return redeem_tx, "Redeem"
    
    def execute_transaction(self, tx: SafeTransaction, action: str):
        response = self.client.execute([tx], f"{action} positions")
        response.wait()
        logger.info(f"{action} transaction completed")

