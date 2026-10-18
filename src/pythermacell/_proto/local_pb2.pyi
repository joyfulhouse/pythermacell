from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SessionCmd0(_message.Message):
    __slots__ = ("client_pubkey",)
    CLIENT_PUBKEY_FIELD_NUMBER: _ClassVar[int]
    client_pubkey: bytes
    def __init__(self, client_pubkey: _Optional[bytes] = ...) -> None: ...

class SessionResp0(_message.Message):
    __slots__ = ("status", "device_pubkey", "device_random")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DEVICE_PUBKEY_FIELD_NUMBER: _ClassVar[int]
    DEVICE_RANDOM_FIELD_NUMBER: _ClassVar[int]
    status: int
    device_pubkey: bytes
    device_random: bytes
    def __init__(self, status: _Optional[int] = ..., device_pubkey: _Optional[bytes] = ..., device_random: _Optional[bytes] = ...) -> None: ...

class SessionCmd1(_message.Message):
    __slots__ = ("client_verify_data",)
    CLIENT_VERIFY_DATA_FIELD_NUMBER: _ClassVar[int]
    client_verify_data: bytes
    def __init__(self, client_verify_data: _Optional[bytes] = ...) -> None: ...

class SessionResp1(_message.Message):
    __slots__ = ("status", "device_verify_data")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DEVICE_VERIFY_DATA_FIELD_NUMBER: _ClassVar[int]
    status: int
    device_verify_data: bytes
    def __init__(self, status: _Optional[int] = ..., device_verify_data: _Optional[bytes] = ...) -> None: ...

class Sec1Payload(_message.Message):
    __slots__ = ("msg", "sc0", "sr0", "sc1", "sr1")
    MSG_FIELD_NUMBER: _ClassVar[int]
    SC0_FIELD_NUMBER: _ClassVar[int]
    SR0_FIELD_NUMBER: _ClassVar[int]
    SC1_FIELD_NUMBER: _ClassVar[int]
    SR1_FIELD_NUMBER: _ClassVar[int]
    msg: int
    sc0: SessionCmd0
    sr0: SessionResp0
    sc1: SessionCmd1
    sr1: SessionResp1
    def __init__(self, msg: _Optional[int] = ..., sc0: _Optional[_Union[SessionCmd0, _Mapping]] = ..., sr0: _Optional[_Union[SessionResp0, _Mapping]] = ..., sc1: _Optional[_Union[SessionCmd1, _Mapping]] = ..., sr1: _Optional[_Union[SessionResp1, _Mapping]] = ...) -> None: ...

class S2SessionCmd0(_message.Message):
    __slots__ = ("client_username", "client_pubkey")
    CLIENT_USERNAME_FIELD_NUMBER: _ClassVar[int]
    CLIENT_PUBKEY_FIELD_NUMBER: _ClassVar[int]
    client_username: bytes
    client_pubkey: bytes
    def __init__(self, client_username: _Optional[bytes] = ..., client_pubkey: _Optional[bytes] = ...) -> None: ...

class S2SessionResp0(_message.Message):
    __slots__ = ("status", "device_pubkey", "device_salt")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DEVICE_PUBKEY_FIELD_NUMBER: _ClassVar[int]
    DEVICE_SALT_FIELD_NUMBER: _ClassVar[int]
    status: int
    device_pubkey: bytes
    device_salt: bytes
    def __init__(self, status: _Optional[int] = ..., device_pubkey: _Optional[bytes] = ..., device_salt: _Optional[bytes] = ...) -> None: ...

class S2SessionCmd1(_message.Message):
    __slots__ = ("client_proof",)
    CLIENT_PROOF_FIELD_NUMBER: _ClassVar[int]
    client_proof: bytes
    def __init__(self, client_proof: _Optional[bytes] = ...) -> None: ...

class S2SessionResp1(_message.Message):
    __slots__ = ("status", "device_proof", "device_nonce")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DEVICE_PROOF_FIELD_NUMBER: _ClassVar[int]
    DEVICE_NONCE_FIELD_NUMBER: _ClassVar[int]
    status: int
    device_proof: bytes
    device_nonce: bytes
    def __init__(self, status: _Optional[int] = ..., device_proof: _Optional[bytes] = ..., device_nonce: _Optional[bytes] = ...) -> None: ...

class Sec2Payload(_message.Message):
    __slots__ = ("msg", "sc0", "sr0", "sc1", "sr1")
    MSG_FIELD_NUMBER: _ClassVar[int]
    SC0_FIELD_NUMBER: _ClassVar[int]
    SR0_FIELD_NUMBER: _ClassVar[int]
    SC1_FIELD_NUMBER: _ClassVar[int]
    SR1_FIELD_NUMBER: _ClassVar[int]
    msg: int
    sc0: S2SessionCmd0
    sr0: S2SessionResp0
    sc1: S2SessionCmd1
    sr1: S2SessionResp1
    def __init__(self, msg: _Optional[int] = ..., sc0: _Optional[_Union[S2SessionCmd0, _Mapping]] = ..., sr0: _Optional[_Union[S2SessionResp0, _Mapping]] = ..., sc1: _Optional[_Union[S2SessionCmd1, _Mapping]] = ..., sr1: _Optional[_Union[S2SessionResp1, _Mapping]] = ...) -> None: ...

class S0SessionCmd(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class S0SessionResp(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: int
    def __init__(self, status: _Optional[int] = ...) -> None: ...

class Sec0Payload(_message.Message):
    __slots__ = ("msg", "sc", "sr")
    MSG_FIELD_NUMBER: _ClassVar[int]
    SC_FIELD_NUMBER: _ClassVar[int]
    SR_FIELD_NUMBER: _ClassVar[int]
    msg: int
    sc: S0SessionCmd
    sr: S0SessionResp
    def __init__(self, msg: _Optional[int] = ..., sc: _Optional[_Union[S0SessionCmd, _Mapping]] = ..., sr: _Optional[_Union[S0SessionResp, _Mapping]] = ...) -> None: ...

class SessionData(_message.Message):
    __slots__ = ("sec_ver", "sec0", "sec1", "sec2")
    SEC_VER_FIELD_NUMBER: _ClassVar[int]
    SEC0_FIELD_NUMBER: _ClassVar[int]
    SEC1_FIELD_NUMBER: _ClassVar[int]
    SEC2_FIELD_NUMBER: _ClassVar[int]
    sec_ver: int
    sec0: Sec0Payload
    sec1: Sec1Payload
    sec2: Sec2Payload
    def __init__(self, sec_ver: _Optional[int] = ..., sec0: _Optional[_Union[Sec0Payload, _Mapping]] = ..., sec1: _Optional[_Union[Sec1Payload, _Mapping]] = ..., sec2: _Optional[_Union[Sec2Payload, _Mapping]] = ...) -> None: ...

class CmdGetPropertyCount(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RespGetPropertyCount(_message.Message):
    __slots__ = ("status", "count")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    status: int
    count: int
    def __init__(self, status: _Optional[int] = ..., count: _Optional[int] = ...) -> None: ...

class PropertyInfo(_message.Message):
    __slots__ = ("status", "name", "type", "flags", "value")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    FLAGS_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    status: int
    name: str
    type: int
    flags: int
    value: bytes
    def __init__(self, status: _Optional[int] = ..., name: _Optional[str] = ..., type: _Optional[int] = ..., flags: _Optional[int] = ..., value: _Optional[bytes] = ...) -> None: ...

class CmdGetPropertyValues(_message.Message):
    __slots__ = ("indices",)
    INDICES_FIELD_NUMBER: _ClassVar[int]
    indices: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, indices: _Optional[_Iterable[int]] = ...) -> None: ...

class RespGetPropertyValues(_message.Message):
    __slots__ = ("status", "props")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PROPS_FIELD_NUMBER: _ClassVar[int]
    status: int
    props: _containers.RepeatedCompositeFieldContainer[PropertyInfo]
    def __init__(self, status: _Optional[int] = ..., props: _Optional[_Iterable[_Union[PropertyInfo, _Mapping]]] = ...) -> None: ...

class PropertyValue(_message.Message):
    __slots__ = ("index", "value")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    index: int
    value: bytes
    def __init__(self, index: _Optional[int] = ..., value: _Optional[bytes] = ...) -> None: ...

class CmdSetPropertyValues(_message.Message):
    __slots__ = ("props",)
    PROPS_FIELD_NUMBER: _ClassVar[int]
    props: _containers.RepeatedCompositeFieldContainer[PropertyValue]
    def __init__(self, props: _Optional[_Iterable[_Union[PropertyValue, _Mapping]]] = ...) -> None: ...

class RespSetPropertyValues(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: int
    def __init__(self, status: _Optional[int] = ...) -> None: ...

class LocalCtrlMessage(_message.Message):
    __slots__ = ("msg", "cmd_get_prop_count", "resp_get_prop_count", "cmd_get_prop_vals", "resp_get_prop_vals", "cmd_set_prop_vals", "resp_set_prop_vals")
    MSG_FIELD_NUMBER: _ClassVar[int]
    CMD_GET_PROP_COUNT_FIELD_NUMBER: _ClassVar[int]
    RESP_GET_PROP_COUNT_FIELD_NUMBER: _ClassVar[int]
    CMD_GET_PROP_VALS_FIELD_NUMBER: _ClassVar[int]
    RESP_GET_PROP_VALS_FIELD_NUMBER: _ClassVar[int]
    CMD_SET_PROP_VALS_FIELD_NUMBER: _ClassVar[int]
    RESP_SET_PROP_VALS_FIELD_NUMBER: _ClassVar[int]
    msg: int
    cmd_get_prop_count: CmdGetPropertyCount
    resp_get_prop_count: RespGetPropertyCount
    cmd_get_prop_vals: CmdGetPropertyValues
    resp_get_prop_vals: RespGetPropertyValues
    cmd_set_prop_vals: CmdSetPropertyValues
    resp_set_prop_vals: RespSetPropertyValues
    def __init__(self, msg: _Optional[int] = ..., cmd_get_prop_count: _Optional[_Union[CmdGetPropertyCount, _Mapping]] = ..., resp_get_prop_count: _Optional[_Union[RespGetPropertyCount, _Mapping]] = ..., cmd_get_prop_vals: _Optional[_Union[CmdGetPropertyValues, _Mapping]] = ..., resp_get_prop_vals: _Optional[_Union[RespGetPropertyValues, _Mapping]] = ..., cmd_set_prop_vals: _Optional[_Union[CmdSetPropertyValues, _Mapping]] = ..., resp_set_prop_vals: _Optional[_Union[RespSetPropertyValues, _Mapping]] = ...) -> None: ...
