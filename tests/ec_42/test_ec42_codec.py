# SPDX-License-Identifier: GPL-3.0-or-later
"""EC42 packet, calibration-record and backup validation; no firmware harness."""
import json,struct,tempfile,unittest,zlib
from pathlib import Path
from vi_al_addons.ec_42.protocol import *
P=PROFILES[0]

def seal_record(cells=None, overrides=None, method=0x42):
    raw = bytearray(bytes([0])+be16(550)+be16(500)+be16(550)+bytes([70,70]))
    for v in cells or [0xc384]*P.cells:
        raw.extend(be16(v))
    meta = len(raw)
    raw += be16(P.magic)+be16(method)+bytes(4)+bytes(overrides or [0]*P.cells)
    native = bytearray(raw)
    for i in list(range(1,7,2))+list(range(9,meta+8,2)):
        native[i],native[i+1]=native[i+1],native[i]
    crc = zlib.crc32(native)
    raw[meta+4:meta+8]=be16(crc & 65535)+be16(crc >> 16)
    return bytes(raw)

class CodecTests(unittest.TestCase):
    def test_packet_roundtrip_and_invalid_headers(self):
        raw=encode(Op.PAGE,123,b'123',response=True)
        self.assertEqual(decode(raw),(Op.PAGE,123,0,True,b'123'))
        for index,value in ((0,0),(5,9),(6,0),(9,5),(10,21),(11,2),(31,1)):
            bad=bytearray(raw);bad[index]=value
            with self.subTest(index=index),self.assertRaises(ECError):decode(bad)
        for bad in (raw[:-1],raw+b'0'):
            with self.assertRaises(ECError):decode(bad)
        with self.assertRaises(ECError):encode(Op.PAGE,1,bytes(21))
        with self.assertRaises(ECError):encode(Op.PAGE,1,status=1)

    def test_crc_and_all_byte_corruption(self):
        raw=seal_record()
        decoded=decode_record(raw,P)
        self.assertTrue(decoded.packed)
        self.assertEqual(len(decoded.overrides),96)
        for i in range(len(raw)):
            bad=bytearray(raw);bad[i]^=1
            with self.subTest(offset=i),self.assertRaises(ECError):decode_record(bad,P)

    def test_signed_dimensions_identity_and_semantics(self):
        for p in PROFILES[1:]:
            with self.assertRaises(ECError):decode_record(seal_record(),p)
        for value in (0x0401,0x8001,0xe301,0x4000,1):
            with self.subTest(cell=value),self.assertRaises(ECError):decode_record(seal_record([value]*96),P)
        with self.assertRaises(ECError):decode_record(seal_record(overrides=[100]*96),P)
        self.assertFalse(decode_record(seal_record(method=3),P).packed)
        with self.assertRaises(ECError):decode_record(seal_record(method=4),P)
        self.assertIsNone(profile_for_uid(bytes.fromhex('0011223344556677')))
        self.assertEqual(profile_for_uid(int.from_bytes(P.uid,'little')),P)

    def test_backup_raw_export_restore_admission(self):
        raw=seal_record()
        doc=backup_document(raw,P)
        self.assertEqual(load_backup(doc,P),raw)
        for key,value in (('uid','00'*8),('crc32','0'),('rows',5),('format','legacy')):
            bad=dict(doc);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ECError):load_backup(bad,P)
        invalid=backup_document(bytes(P.record_size),P)
        self.assertFalse(invalid['restorable'])
        with self.assertRaises(ECError):load_backup(invalid,P)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'backup.json';save_backup(path,raw,P)
            self.assertEqual(load_backup(json.loads(path.read_text()),P),raw)
            with self.assertRaises(FileExistsError):save_backup(path,raw,P)

    def test_transport_failure_never_retries(self):
        calls=[]
        def fail(q):calls.append(q);raise ECError('timeout')
        c=Client(fail,P);c.ready=True
        with self.assertRaises(ECError):c.request(Op.CONTROL,b'\x01')
        with self.assertRaises(ECError):c.request(Op.CONTROL,b'\x01')
        self.assertEqual(len(calls),1)
        c=Client(lambda q:encode(Op.STATUS,0,response=True),P);c.ready=True
        with self.assertRaises(ECError):c.status()
        self.assertFalse(c.healthy)

    def test_unknown_board_sends_no_ec_packet(self):
        calls=[]
        def wrong(q):calls.append(q);return bytes([6])+bytes(31)
        c=Client(wrong,P)
        with self.assertRaises(ECError):c.identify()
        self.assertEqual(calls,[b'\xfe\x00'.ljust(32,b'\0')])

    def test_old_firmware_rejected_before_write(self):
        calls=[]
        def peer(q):
            calls.append(q)
            if q[:2]==b'\xfe\0':return bytes([6])+bytes(3)+P.uid+bytes(20)
            op,seq,*_=decode(q)
            payload=b'QEC2\x08'+be16(6)+be16(16)+be16(1023)+bytes([1])+be16(0x46)+bytes([5,1])
            return encode(op,seq,payload,response=True)
        c=Client(peer,P)
        with self.assertRaises(ECError):c.identify()
        self.assertEqual(len(calls),2)
        with self.assertRaises(ECError):c.set_actuation(0xffff,50)
        self.assertFalse(any(q[:5]==b'\xcaEC42' and q[6] in (0x20,0x29,0x2a) for q in calls))

    def test_actuation_endpoint(self):
        self.assertEqual(percent_q(99),1022)
        self.assertEqual(percent_q(50),512)
        self.assertEqual(affine(512,100,900),500)
        for percent in (0,100,-1):
            with self.assertRaises(ECError):percent_q(percent)
