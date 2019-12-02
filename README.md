# algobot
Python framework for handling the stream of Algorand transactions

``` Python
import algobot
bot = Algobot('algod_token', 'http://algod_address:8080', txn_handlers=[lambda b,t, ctx:None])
bot.loop()
```
