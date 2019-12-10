# algobot
Python framework for handling the stream of Algorand transactions

Generally it works like an http server framework where you register a handler and the framework hands event data to your handler functions.

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
        block_handlers=[block_handler],
        txn_handlers=[txn_handler],
    )
    bot.loop()
```
