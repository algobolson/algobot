#!/usr/bin/env python3
#
# pip install py-algorand-sdk

import argparse
import base64
import glob
import json
import logging
import msgpack
import os
import signal
import sys
import time

import algosdk

logger = logging.getLogger(__name__)

# algod = get_algod(os.path.join(os.getenv('HOME'),'Algorand/n3/Node1'))
# algod = get_algod(os.path.join(os.getenv('HOME'),'mainnet'))
# print(json.dumps(algod.status(), indent=2))
# b=algod.block_info(algod.status()['lastRound'])
# print(json.dumps(b, indent=2))
def get_algod(algorand_data):
    addr = open(os.path.join(algorand_data, 'algod.net'), 'rt').read().strip()
    if not addr.startswith('http'):
        addr = 'http://' + addr
    token = open(os.path.join(algorand_data, 'algod.token'), 'rt').read().strip()
    return algosdk.algod.AlgodClient(token, addr)

# b = nextblock(algod, b['round'])
def nextblock(algod, lastround=None):
    if lastround is None:
        lastround = algod.status()['lastRound']
        logger.debug('nextblock status lastRound %s', lastround)
    else:
        try:
            b = algod.block_info(lastround+1)
            return b
        except:
            pass
    status = algod.status_after_block(lastround)
    nbr = status['lastRound']
    b = algod.block_info(nbr)
    return b

def maybedecode(x):
    if isinstance(x, bytes):
        return x.decode()
    return x

def unmsgpack(ob):
    "convert dict from msgpack.loads() with byte string keys to text string keys"
    if isinstance(ob, dict):
        od = {}
        for k,v in ob.items():
            k = maybedecode(k)
            okv = False
            if (not okv) and (k == 'note'):
                try:
                    v = unmsgpack(msgpack.loads(v))
                    okv = True
                except:
                    pass
            if (not okv) and k in ('type', 'note'):
                try:
                    v = v.decode()
                    okv = True
                except:
                    pass
            if not okv:
                v = unmsgpack(v)
            od[k] = v
        return od
    if isinstance(ob, list):
        return [unmsgpack(v) for v in ob]
    #if isinstance(ob, bytes):
    #    return base64.b64encode(ob).decode()
    return ob

def make_ob_json_polite(ob):
    if isinstance(ob, dict):
        return {k:make_ob_json_polite(v) for k,v in ob.items()}
    if isinstance(ob, list):
        return [make_ob_json_polite(x) for x in ob]
    if isinstance(ob, bytes):
        return base64.b64encode(ob).decode()
    return ob

class Algobot:
    def __init__(self, algorand_data, block_handlers=None, txn_handlers=None, progress_log_path=None, raw_api=None):
        self.algorand_data = algorand_data
        self._algod = None
        self.block_handlers = block_handlers or list()
        self.txn_handlers = txn_handlers or list()
        self.progress_log_path = progress_log_path
        self._progresslog = None
        self._progresslog_write_count = 0
        self.go = True
        self.raw_api = raw_api
        self.algod_has_block_raw = None
        self.blockfiles = None
        return

    def algod(self):
        if self._algod is None:
            self._algod = get_algod(self.algorand_data)
        return self._algod

    def rawblock(self, xround):
        "if possible fetches and returns raw block msgpack including block and cert; otherwise None"
        algod = self.algod()
        if self.algod_has_block_raw or (self.algod_has_block_raw is None):
            response = algod.algod_request("GET", "/block/" + str(xround), params={'raw':1}, raw_response=True)
            contentType = response.getheader('Content-Type')
            if contentType == 'application/json':
                logger.debug('got json response, disabling rawblock')
                self.algod_has_block_raw = False
                return None
            if contentType == 'application/x-algorand-block-v1':
                self.algod_has_block_raw = True
                raw = response.read()
                block = unmsgpack(msgpack.loads(raw))
                return block
            raise Exception('unknown response content type {!r}'.format(contentType))
        logger.debug('rawblock passing out')
        return None

    def eitherblock(self, xround):
        "return raw block or json info block"
        if self.algod_has_block_raw or (self.raw_api != False):
            return self.rawblock(xround)
        if (self.raw_api != False) and (self.algod_has_block_raw is None):
            xb = self.rawblock(xround)
            if self.algod_has_block_raw:
                return xb
        return self.algod().block_info(xround)

    def nextblock_from_files(self):
        if not self.blockfiles:
            logger.debug('empty blockfiles')
            self.go = False
            return {'block':{'rnd':None}}
            #raise Exception("end of blockfiles")
        bf = self.blockfiles[0]
        logger.debug('block from file %s', bf)
        self.blockfiles = self.blockfiles[1:]
        with open(bf, 'rb') as fin:
            raw = fin.read()
        try:
            return unmsgpack(msgpack.loads(raw))
        except Exception as e:
            logger.debug('%s: failed to msgpack decode, %s', bf, e)
        return json.loads(raw.decode())

    def nextblock(self, lastround=None, retries=3):
        "from block_info json api simplified block"
        trycount = 0
        while (trycount < retries) and self.go:
            trycount += 1
            try:
                return self._nextblock_inner(lastround)
            except Exception as e:
                if trycount >= retries:
                    raise
                else:
                    logger.warn('error in nextblock(%r) (retrying): %s', lastround, e)
        return None

    def _nextblock_inner(self, lastround):
        if self.blockfiles is not None:
            return self.nextblock_from_files()
        algod = self.algod()
        # TODO: algod block raw
        if lastround is None:
            lastround = algod.status()['lastRound']
            logger.debug('nextblock status lastRound %s', lastround)
        else:
            try:
                return self.eitherblock(lastround+1)
            except:
                pass
        status = algod.status_after_block(lastround)
        nbr = status['lastRound']
        while (nbr > lastround+1) and self.go:
            # try lastround+1 one last time
            try:
                return self.eitherblock(lastround+1)
            except:
                break
        b = self.eitherblock(nbr)
        return b

    def loop(self):
        lastround = self.recover_progress()
        try:
            self._loop_inner(lastround)
        finally:
            self.close()

    def _loop_inner(self, lastround):
        while self.go:
            b = self.nextblock(lastround)
            if b is None:
                print("got None nextblock. exiting")
                return
            nowround = blockround(b)
            if (lastround is not None) and (nowround != lastround + 1):
                logger.info('round jump %d to %d', lastround, nowround)
            for bh in self.block_handlers:
                bh(self, b)
            bb = b.get('block')
            if bb:
                # raw block case
                transactions = bb.get('txns', [])
            else:
                # json block_info case
                txns = b.get('txns', {})
                transactions = txns.get('transactions', [])
            for txn in transactions:
                for th in self.txn_handlers:
                    th(self, b, txn)
            self.record_block_progress(nowround)
            lastround = nowround

    def record_block_progress(self, round_number):
        if self._progresslog_write_count > 100000:
            if self._progresslog is not None:
                self._progresslog.close()
                self._progresslog = None
            nextpath = self.progress_log_path + '_next_' + time.strftime('%Y%m%d_%H%M%S', time.gmtime())
            nextlog = open(nextpath, 'xt')
            nextlog.write('{}\n'.format(round_number))
            nextlog.flush()
            nextlog.close() # could probably leave this open and keep writing to it
            os.replace(nextpath, self.progress_log_path)
            self._progresslog_write_count = 0
            # new log at standard location will be opened next time
            return
        if self._progresslog is None:
            if self.progress_log_path is None:
                return
            self._progresslog = open(self.progress_log_path, 'at')
            self._progresslog_write_count = 0
        self._progresslog.write('{}\n'.format(round_number))
        self._progresslog.flush()
        self._progresslog_write_count += 1

    def recover_progress(self):
        if self.progress_log_path is None:
            return None
        try:
            with open(self.progress_log_path, 'rt') as fin:
                fin.seek(0, 2)
                endpos = fin.tell()
                fin.seek(max(0, endpos-100))
                raw = fin.read()
                lines = raw.splitlines()
                return int(lines[-1])
        except Exception as e:
            logger.info('could not recover progress: %s', e)
        return None

    def close(self):
        if self._progresslog is not None:
            self._progresslog.close()
            self._progresslog = None

def blockround(b):
    bb = b.get('block')
    if bb:
        # raw mode
        return bb.get('rnd')
    else:
        # block_info json mode
        return b.get('round')

# block_printer is an example block handler; it takes two args, the bot and the block
def block_printer(bot, b):
    txns = b.get('txns')
    if txns:
        print(json.dumps(b, indent=2))
    else:
        bround = b.get('round')
        if bround % 10 == 0:
            print(bround)

# block_counter is an example block handler; it takes two args, the bot and the block
def block_counter(bot, b):
    bround = blockround(b)
    if bround % 10 == 0:
        print(bround)

# big_tx_printer is an example txn handler; it takes three args, the bot the block and the transaction
def big_tx_printer(bot, b, tx):
    txn = tx.get('txn')
    if txn:
        # raw style
        amount = txn.get('amt')
        if amount is not None and amount > 10000000:
            print(json.dumps(make_ob_json_polite(tx), indent=2))
        return
    # block_info style
    payment = tx.get('payment')
    if not payment:
        return
    amount = payment.get('amount')
    if amount > 10000000:
        print(json.dumps(tx, indent=2))

def make_arg_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('-d', '--algod', default=None, help='algod data dir')
    ap.add_argument('--verbose', default=False, action='store_true')
    ap.add_argument('--progress-file', default=None, help='file to write progress to')
    ap.add_argument('--blockfile-glob', default=None, help='file glob of block files')
    ap.add_argument('--raw-api', default=False, action='store_true', help='use raw msgpack api with more data but different layout than json block_info api')
    return ap

def setup(args, block_handlers=None, txn_handlers=None):
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    algorand_data = args.algod or os.getenv('ALGORAND_DATA')
    if not algorand_data:
        sys.stderr.write('must specify algod data dir by $ALGORAND_DATA or -d/--algod\n')
        sys.exit(1)

    if block_handlers is None and txn_handlers is None:
        txn_handlers = [big_tx_printer]
        block_handlers = [block_counter]
    bot = Algobot(
        algorand_data,
        block_handlers=block_handlers,
        txn_handlers=txn_handlers,
        progress_log_path=args.progress_file,
        raw_api=args.raw_api,
    )

    if args.blockfile_glob:
        bot.blockfiles = glob.glob(args.blockfile_glob)

    killcount = [0]
    def gogently(signum,stackframe):
        count = killcount[0] + 1
        if count == 1:
            sys.stderr.write('signal received. starting graceful shutdown\n')
            bot.go = False
            killcount[0] = count
            return
        sys.stderr.write('second signal received. bye\n')
        sys.exit(1)
    signal.signal(signal.SIGTERM, gogently)
    signal.signal(signal.SIGINT, gogently)

    return bot

def main(block_handlers=None, txn_handlers=None, arghook=None):
    ap = make_arg_parser()
    args = ap.parse_args()

    if arghook is not None:
        arghook(args)

    bot = setup(args, block_handlers, txn_handlers)
    bot.loop()
    return

if __name__ == '__main__':
    main()
