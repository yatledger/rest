from pydantic import (BaseModel, PositiveInt)
from pymongo import MongoClient
from nacl.encoding import HexEncoder
from nacl.signing import VerifyKey
import hashlib
from typing import Optional, List

cli = MongoClient('localhost', 27017)

db = cli.yat
txs = db.tx
txs2 = db.tx2

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

tx = txs.find()
prev_hash = '16b68baaccfa3795d7affc68dde5d89b81e9886c7227c12a1a1aec3b9155383952f477ab667600e1416d33b04c2bebef9a1a9b25a1a248e105a5314aee00cf33'
for t in tx[1:]:
    t = Tx(**t)
    msg = ''
    if t.msg: msg = str(t.msg)
    m = t.credit + t.debit + str(t.amount) + msg + str(t.time)
    m_hash = tob2b(m)
    this_hash = tob2b(prev_hash + m_hash)
    prev_hash = this_hash
    TX = {
        'credit': t.credit,
        'debit': t.debit,
        'amount': t.amount,
        'time': t.time,
        'sign': t.sign,
        'hash': this_hash,
        'msg': msg
    }
    tx_id = txs2.insert_one(TX).inserted_id
    print(tx_id)