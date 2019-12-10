# algobot
Python framework for handling the stream of Algorand transactions

Requires Algorand Python sdk:
``` bash
pip install py-algorand-sdk
```

Basic template:
``` Python
import algobot
def block_handler(bot, block):
    pass
def txn_handler(bot, block, txn):
    pass
algobot.main(block_handlers=[block_handler], txn_handlers=[txn_handler])
```

Customized flow:
``` Python
def main():
    ap = algobot.make_arg_parser()
    # ap.add_argument(...)
    args = ap.parse_args()
    # maybe do stuff with args you added or override defaults
    bot = algobot.setup(
        args,
        block_handlers=[algobot.block_counter],
        txn_handlers=[print_teal_txns],
    )
    bot.loop()
```
