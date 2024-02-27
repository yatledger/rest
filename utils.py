from pydantic import (BaseModel, PositiveInt, conint)
from pymongo import MongoClient
from nacl.encoding import HexEncoder
from nacl.signing import VerifyKey
import hashlib
from typing import Optional
from tqdm import tqdm

cli = MongoClient('localhost', 27017)

db = cli.yat
txs = db.tx2

class Tx(BaseModel):
    credit: str
    debit: str
    amount: PositiveInt
    time: int
    sign: str
    hash: Optional[str]
    msg: Optional[str]
    #type

def tob2b(t):
    h = hashlib.blake2b()
    h.update(bytes(t.encode("utf-8")))
    return h.digest().hex()

def verify():
    tx = txs.find()
    prev_hash = ''
    txt = []
    for t in tx:
        sok = f'SIGN FAIL'
        hok = f'HASH FAIL'
        t = Tx(**t)
        msg = ''
        if t.msg: msg = str(t.msg)
        verify_key = VerifyKey(bytes(t.credit.encode("utf-8")), encoder=HexEncoder)
        m = t.credit + t.debit + str(t.amount) + msg + str(t.time)
        v = verify_key.verify(bytes(t.sign.encode("utf-8")), encoder=HexEncoder).decode("utf-8")
        #print(f'{m}\n{v}')
        if v == m:
            sok = f'SIGN OK'
        else:
            print('SIGN F')

        m_hash = tob2b(m)
        this_hash = tob2b(prev_hash + m_hash)
        print(this_hash, t.hash)
        if this_hash == t.hash:
            hok = f'HASH OK'
        else:
            print('HASH F')
        prev_hash = this_hash
        txt.append(f'{t.time} {sok} {hok} FROM {t.credit} TO {t.debit} {t.amount}')
    print(*txt, sep='\n')

verify()