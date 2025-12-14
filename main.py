import os
import time
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import Payment
from xrpl.transaction import submit_and_wait
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# ================= CONFIG =================
XRPL_RPC = "https://s1.ripple.com:51234"
ACCOUNT_RESERVE_XRP = 10
TX_FEE_BUFFER_DROPS = 20
POLL_INTERVAL = 2
# ==========================================

# 🔐 Load secrets securely
MNEMONIC = os.getenv("XRPL_MNEMONIC")
DESTINATION = os.getenv("XRPL_DESTINATION")

if not MNEMONIC or not DESTINATION:
    raise RuntimeError("Missing XRPL secrets in environment variables")

print("🔐 Secrets loaded securely from environment")

# ---- Key derivation ----
seed_bytes = Bip39SeedGenerator(MNEMONIC).Generate()

bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.RIPPLE)
acct = (bip44_ctx.Purpose().Coin().Account(0).Change(
    Bip44Changes.CHAIN_EXT).AddressIndex(0))

priv_key_hex = acct.PrivateKey().Raw().ToBytes().hex().upper()
pub_key_hex = acct.PublicKey().RawCompressed().ToBytes().hex().upper()

wallet = Wallet(
    public_key=pub_key_hex,
    private_key=priv_key_hex,
    seed=None,
    algorithm="ed25519",
)

print("📬 Wallet address:", wallet.classic_address)

# ---- XRPL client ----
client = JsonRpcClient(XRPL_RPC)
reserve_drops = ACCOUNT_RESERVE_XRP * 1_000_000

print("⏳ Monitoring account balance...")

while True:
    try:
        info = client.request(
            AccountInfo(account=wallet.classic_address,
                        ledger_index="validated")).result

        if "account_data" not in info:
            print("⏳ Account not activated yet")
            time.sleep(POLL_INTERVAL)
            continue

        balance = int(info["account_data"]["Balance"])
        sendable = max(balance - reserve_drops - TX_FEE_BUFFER_DROPS, 0)

        if sendable <= 0:
            print("💤 Balance locked by reserve")
            time.sleep(POLL_INTERVAL)
            continue

        print(f"⚡ Sweeping {sendable / 1_000_000:.6f} XRP")

        tx = submit_and_wait(
            Payment(
                account=wallet.classic_address,
                destination=DESTINATION,
                amount=str(sendable),
            ), client, wallet)

        print("✅ Sweep complete:", tx.result["hash"])
        break

    except Exception as e:
        print("⚠️ Temporary error:", e)
        time.sleep(2)
