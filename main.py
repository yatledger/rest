from fastapi import Request, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from starlette.responses import HTMLResponse

from aio_pika import connect_robust, Message, DeliveryMode

import json
from typing import Optional, List

from pydantic import BaseModel, PositiveInt, BaseSettings

import motor.motor_asyncio

from nacl.encoding import HexEncoder
from nacl.signing import VerifyKey
#from nacl.hash import blake2b
#blake2b(b'049700da9fa6bb1ba5177e072b54e83372b5af36a8812cb85948abacbc2e1bcb4100000000000', digest_size=32, encoder=HexEncoder).decode("utf-8")

import hashlib
import time

#from graphene import ObjectType, String, Schema, List, Field

class Settings(BaseSettings):
    t_cur: float = 0
    t_prev: float = 0
    t_count: int = 1
    t_dif: float  = 0

set = Settings()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup() -> None:
    global mq
    connection = await connect_robust("amqp://guest:guest@localhost/")
    mq = await connection.channel()
    queue = await mq.declare_queue("tx", durable=True)
    

cli = motor.motor_asyncio.AsyncIOMotorClient('localhost', 27017)

db = cli.yat
txs = db.tx2
usrs = db.users

def get_time():
    return round(time.time() * 1000)

def tob2b(t):
    h = hashlib.blake2b(digest_size=32)
    h.update(bytes(t.encode("utf-8")))
    return h.digest().hex()

async def get_balance(addr):
    income_q = [{
        '$match': {
            'debit': addr
        }}, {
        '$group': {
            '_id': None, 
            'sum': {
                '$sum': '$amount'
            }
        }
    }]
    outcome_q = [{
        '$match': {
            'credit': addr
        }}, {
        '$group': {
            '_id': None, 
            'sum': {
                '$sum': '$amount'
            }
        }
    }]
    if (income := await txs.aggregate(income_q).to_list(1)):
        #print(f'in: {income}')
        income = income[0]['sum']
        if (outcome := await txs.aggregate(outcome_q).to_list(1)):
            #print(outcome)
            outcome = outcome[0]['sum']
            return income - outcome
        else:
            return income
    else:
        return 0

async def set_user(addr, req, c, s):
    verify_key = VerifyKey(bytes(addr.encode("utf-8")), encoder=HexEncoder)
    v = verify_key.verify(bytes(s.encode("utf-8")), encoder=HexEncoder).decode("utf-8")
    if v == c:
        if await usrs.find_one({"addr": addr}):
            result = await usrs.update_one({"addr": addr}, {"$set": {req: c}})
            #print(dir(result))
            if result.matched_count == 1:
                return {'detail': [{'success': 1, 'msg': f'{req} ok'}]}
        else:
            result = await usrs.insert_one({"addr": addr, req: c})
            if result.inserted_id:
                return {'detail': [{'success': 1, 'msg': f'{req} ok'}]}

    else:
        return {'detail': [{'success': 0, 'msg': 'bad sign'}]} 

class Tx(BaseModel):
    credit: str
    debit: str
    amount: PositiveInt
    time: int
    sign: str
    hash: Optional[str]
    msg: Optional[str]
    #type

class UsContent(BaseModel):
    addr: str
    req: str
    time: int
    content: str
    sign: str

class User(BaseModel):
    addr: str
    name: Optional[str]
    cover: Optional[str]
    desc: Optional[str]

@app.get("/")
async def root():
    return HTMLResponse(content = "POST /send<br />GET /tx")

@app.get("/tx", response_model=List[Tx])
async def tx_all():
    return await txs.find({'$query': {}, '$orderby': {'_id': -1}}).to_list(None)

@app.get("/tx/{addr}", response_model=List[Tx])
async def tx_addr(addr):
    tx = await txs.find({'$query': {
        '$or': [{'credit': addr}, {'debit': addr}]},
        '$orderby': {'_id': -1}
    }).to_list(10)
    return tx

@app.get("/balance/{addr}")
async def balance(addr):
    out = await get_balance(addr)
    return out
    #raise HTTPException(status_code=404, detail=f"Address {addr} not found")

@app.get("/user/{addr}", response_model=User)
async def get_user(addr):
    return await usrs.find_one({"addr": addr})

@app.get("/users", response_model=List[User])
async def get_users():
    return await usrs.find().to_list(None)

@app.post("/user/")
async def user(u: UsContent):
    b = await get_balance(u.addr)
    if u.req == 'name' and b >= 100:
        return await set_user(u.addr, 'name', u.content, u.sign)
    if u.req == 'desc' and b >= 250:
        return await set_user(u.addr, 'desc', u.content, u.sign)
    if u.req == 'cover' and b >= 500:
        return await set_user(u.addr, 'cover', u.content, u.sign)
    return {'detail': [{'success': 0, 'msg': f'no money'}]}

@app.post("/send/")
async def send(tx: Tx):
    set.t_cur = time.time()
    #print(t_prev, t_cur, t_count, t_dif)
    if set.t_prev:
        set.t_dif += set.t_prev - set.t_cur
        if set.t_count % 100 == 0: print(set.t_dif / set.t_count)
        set.t_count += 1
    set.t_prev = set.t_cur
    try:
        uniq = await txs.find_one({"time": tx.time})
        if uniq:
            return {'detail': [{'success': 0, 'msg': f'not uniq ({tx.time})'}]}
        if tx.credit == tx.debit:
            return {'detail': [{'success': 0, 'msg': f'not for yourself'}]}

        if tx.msg and tx.amount < 100:
            return {'detail': [{'success': 0, 'msg': f'bad amount'}]}

        try:
            addr_len = len(HexEncoder.decode(tx.debit))
            if addr_len != 32:
                return {'detail': [{'success': 0, 'msg': f'bad address size'}]}
        except:
            return {'detail': [{'success': 0, 'msg': f'bad address'}]}

        m = tx.credit + tx.debit + str(tx.amount) + str(tx.msg) + str(tx.time)

        verify_key = VerifyKey(bytes(tx.credit.encode("utf-8")), encoder=HexEncoder)
        v = verify_key.verify(bytes(tx.sign.encode("utf-8")), encoder=HexEncoder).decode("utf-8")
        if v == m:
            balance = await get_balance(tx.credit)
            if balance == 0 or balance < tx.amount:
                return {'detail': [{'success': 0, 'msg': f'bad balance'}]}
            await mq.default_exchange.publish(Message(json.dumps(jsonable_encoder(tx)).encode("utf-8"), delivery_mode=DeliveryMode.PERSISTENT),routing_key="tx")
            return {'detail': [{'success': 1, 'msg': 'ok'}]}
        else:
            return {'detail': [{'success': 0, 'msg': 'bad sign'}]}     

    except Exception as e:
        return {'detail': [{'success': 0, 'msg': str(e)}]}