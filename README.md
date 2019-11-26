# algobot
Python framework for handling the stream of Algorand transactions

``` Python
import algobot
bot = algobot.main(block_handlers=[lambda b:None], txn_handlers=[lambda b,t:None])
```
