# algobot
Python framework for handling the stream of Algorand transactions

``` Python
import algobot
bot = algobot.Algobot('path/to/algod/data', txn_handlers=[lambda b,t:None])
bot.loop()
```
