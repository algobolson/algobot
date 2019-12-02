#!/usr/bin/env python3
#
# pip install py-algorand-sdk

import json
import logging
import signal
import sys

import algosdk

logger = logging.getLogger(__name__)


# b = nextblock(algod, b['round'])
def nextblock(algod, lastround=None):
    if lastround is None:
        lastround = algod.status()['lastRound']
        logger.debug('nextblock status lastRound %s', lastround)
    else:
        try:
            b = algod.block_info(lastround + 1)
            return b
        except:
            pass
    status = algod.status_after_block(lastround)
    nbr = status['lastRound']
    b = algod.block_info(nbr)
    return b


class Algobot:
    def __init__(self, token, address, headres=None, block_handlers=None, txn_handlers=None, progress_log_path=None):
        self.algod_address = address
        self.algod_token = token
        self.algod_headers = headres
        self._algod = None
        self.block_handlers = block_handlers or list()
        self.txn_handlers = txn_handlers or list()
        self.progress_log_path = progress_log_path
        self._progresslog = None
        self.go = True
        return

    def algod(self):
        if self._algod is None:
            self._algod = algosdk.algod.AlgodClient(self.algod_token, self.algod_address, headers=self.algod_headers)
        return self._algod

    def loop(self):
        algod = self.algod()
        lastround = self.recover_progress()
        while self.go:
            b = nextblock(algod, lastround)
            for bh in self.block_handlers:
                bh(b)
            txns = b.get('txns')
            if txns:
                for txn in txns.get('transactions', []):
                    for th in self.txn_handlers:
                        th(b, txn, {"algod": algod})
            lastround = b['round']
            self.record_block_progress(lastround)
        self.close()

    def record_block_progress(self, round_number):
        if self._progresslog is None:
            if self.progress_log_path is None:
                return
            self._progresslog = open(self.progress_log_path, 'at')
        # TODO: if the file is very long, start a new one and move-clobber it over
        self._progresslog.write('{}\n'.format(round_number))
        self._progresslog.flush()

    def recover_progress(self):
        if self.progress_log_path is None:
            return None
        try:
            with open(self.progress_log_path, 'rt') as fin:
                fin.seek(0, 2)
                endpos = fin.tell()
                fin.seek(max(0, endpos - 100))
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


# block_printer is an example block handler; it takes one arg, the block
def block_printer(b):
    txns = b.get('txns')
    if txns:
        print(json.dumps(b, indent=2))
    else:
        bround = b.get('round')
        if bround % 10 == 0:
            print(bround)


# big_tx_printer is an example txn handler; it takes two args, the block and the transaction
def big_tx_printer(b, tx, ctx=None):
    payment = tx.get('payment')
    if not payment:
        return
    amount = payment.get('amount')
    if amount > 10000000:
        print(json.dumps(tx, indent=2))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('-a', '--addr', default=None, help='algod addr')
    ap.add_argument('-t', '--token', default=None, help='algod token')
    ap.add_argument('--purestake', default=False, help='True if a Purestake token is provided', action='store_true')
    ap.add_argument('--verbose', default=False, action='store_true')
    ap.add_argument('--progress-file', default=None, help='file to write progress to')
    args = ap.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Handle purestake
    headers = None
    token = ""
    if args.token is not None:
        if not args.purestake:
            token = args.token
        else:
            headers = {"X-API-Key": args.token, }

    # bot = Algobot(algorand_data, block_handlers=[block_printer])
    bot = Algobot(
        token,
        args.addr,
        headers,
        txn_handlers=[big_tx_printer],
        progress_log_path=args.progress_file,
    )
    killcount = [0]

    def gogently(signum, stackframe):
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
    bot.loop()
    return


if __name__ == '__main__':
    main()
