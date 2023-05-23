import dataclasses
from collections.abc import Iterable
from typing import Literal

from algokit_utils import ApplicationSpecification, OnCompleteActionName

from algokit_client_generator import utils
from algokit_client_generator.document import DocumentParts, Part
from algokit_client_generator.spec import ABIContractMethod, ABIStruct, ContractMethod, get_contract_methods

ESCAPED_QUOTE = r"\""


@dataclasses.dataclass(kw_only=True)
class GenerationSettings:
    indent: str = "    "
    max_line_length: int = 80

    @property
    def indent_length(self) -> int:
        return len(self.indent)


class GenerateContext:
    def __init__(self, app_spec: ApplicationSpecification):
        self.app_spec = app_spec
        # TODO: track these as they are emitted?
        self.used_module_symbols = {
            "_APP_SPEC_JSON",
            "APP_SPEC",
            "_TArgs",
            "_TArgsHolder",
            "_TResult",
            "_ArgsBase",
            "_as_dict",
            "_filter_none",
            "_convert_on_complete",
            "_convert_deploy_args",
            "DeployCreate",
            "Deploy",
            "GlobalState",
            "LocalState",
        }
        self.used_client_symbols = {
            "__init__",
            "app_spec",
            "app_client",
            "algod_client",
            "app_id",
            "app_address",
            "sender",
            "signer",
            "suggested_params",
            "no_op",
            "clear_state",
            "deploy",
            "get_global_state",
            "get_local_state",
        }
        self.client_name = utils.get_unique_symbol_by_incrementing(
            self.used_module_symbols, utils.get_class_name(self.app_spec.contract.name, "client")
        )
        self.methods = get_contract_methods(app_spec, self.used_module_symbols, self.used_client_symbols)
        self.disable_linting = True


def generated_comment(context: GenerateContext) -> DocumentParts:
    yield "# This file was automatically generated by algokit-client-generator."
    yield "# DO NOT MODIFY IT BY HAND."


def disable_linting(context: GenerateContext) -> DocumentParts:
    yield "# flake8: noqa"  # this works for flake8 and ruff
    yield "# fmt: off"  # disable formatting
    yield '# mypy: disable-error-code="no-any-return, no-untyped-call"'  # disable common type warnings


def imports(context: GenerateContext) -> DocumentParts:
    yield utils.lines(
        """import base64
import dataclasses
import decimal
import typing
from abc import ABC, abstractmethod

import algokit_utils
import algosdk
from algosdk.atomic_transaction_composer import TransactionSigner, TransactionWithSigner"""
    )


def typed_argument_class(abi: ABIContractMethod) -> DocumentParts:
    assert abi
    yield "@dataclasses.dataclass(kw_only=True)"
    yield f"class {abi.args_class_name}(_ArgsBase[{abi.python_type}]):"
    yield Part.IncIndent
    if abi.method.desc:
        yield utils.docstring(abi.method.desc)
        yield Part.Gap1
    if abi.args:
        for arg in abi.args:
            yield Part.InlineMode
            yield f"{arg.name}: {arg.python_type}"
            if arg.has_default:
                yield " | None = None"
            yield Part.RestoreLineMode
            if arg.desc:
                yield utils.docstring(arg.desc)
        yield Part.Gap1
    yield "@staticmethod"
    yield "def method() -> str:"
    yield Part.IncIndent
    yield Part.InlineMode
    yield "return "
    yield utils.string_literal(abi.method.get_signature())
    yield Part.DecIndent
    yield Part.DecIndent
    yield Part.RestoreLineMode


def helpers(context: GenerateContext) -> DocumentParts:
    has_abi_create = any(m.abi for m in context.methods.create)
    has_abi_update = any(m.abi for m in context.methods.update_application)
    has_abi_delete = any(m.abi for m in context.methods.delete_application)
    if context.methods.has_abi_methods:
        yield '_TReturn = typing.TypeVar("_TReturn")'
        yield Part.Gap2
        yield utils.indented(
            """
class _ArgsBase(ABC, typing.Generic[_TReturn]):
    @staticmethod
    @abstractmethod
    def method() -> str:
        ..."""
        )
    yield Part.Gap2
    yield '_TArgs = typing.TypeVar("_TArgs", bound=_ArgsBase[typing.Any])'
    yield Part.Gap2
    yield utils.indented(
        """
@dataclasses.dataclass(kw_only=True)
class _TArgsHolder(typing.Generic[_TArgs]):
    args: _TArgs
"""
    )
    yield Part.Gap2

    if has_abi_create:
        yield utils.indented(
            """
@dataclasses.dataclass(kw_only=True)
class DeployCreate(algokit_utils.DeployCreateCallArgs, _TArgsHolder[_TArgs], typing.Generic[_TArgs]):
    pass
"""
        )
        yield Part.Gap2
    if has_abi_update or has_abi_delete:
        yield utils.indented(
            """
@dataclasses.dataclass(kw_only=True)
class Deploy(algokit_utils.DeployCallArgs, _TArgsHolder[_TArgs], typing.Generic[_TArgs]):
    pass"""
        )
        yield Part.Gap2

    yield Part.Gap2
    yield utils.indented(
        """
def _filter_none(value: dict | typing.Any) -> dict | typing.Any:
    if isinstance(value, dict):
        return {k: _filter_none(v) for k, v in value.items() if v is not None}
    return value"""
    )
    yield Part.Gap2
    yield utils.indented(
        """
def _as_dict(data: typing.Any, *, convert_all: bool = True) -> dict[str, typing.Any]:
    if data is None:
        return {}
    if not dataclasses.is_dataclass(data):
        raise TypeError(f"{data} must be a dataclass")
    if convert_all:
        result = dataclasses.asdict(data)
    else:
        result = {f.name: getattr(data, f.name) for f in dataclasses.fields(data)}
    return _filter_none(result)"""
    )
    yield Part.Gap2
    yield utils.indented(
        """
def _convert_transaction_parameters(
    transaction_parameters: algokit_utils.TransactionParameters | None,
) -> algokit_utils.CommonCallParametersDict:
    return typing.cast(algokit_utils.CommonCallParametersDict, _as_dict(transaction_parameters))"""
    )
    yield Part.Gap2
    yield utils.indented(
        """
def _convert_call_transaction_parameters(
    transaction_parameters: algokit_utils.TransactionParameters | None,
) -> algokit_utils.OnCompleteCallParametersDict:
    return typing.cast(algokit_utils.OnCompleteCallParametersDict, _as_dict(transaction_parameters))"""
    )
    yield Part.Gap2
    yield utils.indented(
        """
def _convert_create_transaction_parameters(
    transaction_parameters: algokit_utils.TransactionParameters | None,
    on_complete: algokit_utils.OnCompleteActionName,
) -> algokit_utils.CreateCallParametersDict:
    result = typing.cast(algokit_utils.CreateCallParametersDict, _as_dict(transaction_parameters))
    on_complete_enum = on_complete.replace("_", " ").title().replace(" ", "") + "OC"
    result["on_complete"] = getattr(algosdk.transaction.OnComplete, on_complete_enum)
    return result
    """
    )
    yield Part.Gap2
    yield utils.indented(
        """
def _convert_deploy_args(
    deploy_args: algokit_utils.DeployCallArgs | None,
) -> algokit_utils.ABICreateCallArgsDict | None:
    if deploy_args is None:
        return None

    deploy_args_dict = typing.cast(algokit_utils.ABICreateCallArgsDict, _as_dict(deploy_args))
    if isinstance(deploy_args, _TArgsHolder):
        deploy_args_dict["args"] = _as_dict(deploy_args.args)
        deploy_args_dict["method"] = deploy_args.args.method()

    return deploy_args_dict"""
    )
    yield Part.Gap2


def named_struct(context: GenerateContext, struct: ABIStruct) -> DocumentParts:
    yield "@dataclasses.dataclass(kw_only=True)"
    yield f"class {struct.struct_class_name}:"
    yield Part.IncIndent
    for field in struct.fields:
        yield f"{field.name}: {field.python_type}"
    yield Part.DecIndent


def typed_arguments(context: GenerateContext) -> DocumentParts:
    # typed args classes
    processed_abi_signatures: set[str] = set()
    processed_abi_structs: set[str] = set()
    for method in context.methods.all_abi_methods:
        abi = method.abi
        assert abi
        abi_signature = abi.method.get_signature()
        if abi_signature in processed_abi_signatures:
            continue
        for struct in abi.structs:
            if struct.struct_class_name not in processed_abi_structs:
                yield named_struct(context, struct)
                yield Part.Gap2
                processed_abi_structs.add(struct.struct_class_name)

        processed_abi_signatures.add(abi_signature)
        yield typed_argument_class(abi)
        yield Part.Gap2

    yield Part.Gap2


def state_type(context: GenerateContext, class_name: str, schema: dict[str, dict]) -> DocumentParts:
    if not schema:
        return

    yield f"class {class_name}:"
    yield Part.IncIndent
    yield "def __init__(self, data: dict[bytes, bytes | int]):"
    yield Part.IncIndent
    for field, value in schema.items():
        key = value["key"]
        if value["type"] == "bytes":
            yield f'self.{field} = ByteReader(typing.cast(bytes, data.get(b"{key}")))'
        else:
            yield f'self.{field} = typing.cast(int, data.get(b"{key}"))'
        desc = value["descr"]
        if desc:
            yield utils.docstring(desc)
    yield Part.DecIndent
    yield Part.DecIndent
    yield Part.Gap2


def state_types(context: GenerateContext) -> DocumentParts:
    app_spec = context.app_spec
    global_schema = app_spec.schema.get("global", {}).get("declared", {})
    local_schema = app_spec.schema.get("local", {}).get("declared", {})
    has_bytes = any(i.get("type") == "bytes" for i in [*global_schema.values(), *local_schema.values()])
    if has_bytes:
        yield utils.indented(
            """
class ByteReader:
    def __init__(self, data: bytes):
        self._data = data

    @property
    def as_bytes(self) -> bytes:
        return self._data

    @property
    def as_str(self) -> str:
        return self._data.decode("utf8")

    @property
    def as_base64(self) -> str:
        return base64.b64encode(self._data).decode("utf8")

    @property
    def as_hex(self) -> str:
        return self._data.hex()"""
        )
        yield Part.Gap2
    yield state_type(context, "GlobalState", global_schema)
    yield state_type(context, "LocalState", local_schema)


def typed_client(context: GenerateContext) -> DocumentParts:
    yield utils.indented(
        f"""
class {context.client_name}:
    @typing.overload
    def __init__(
        self,
        algod_client: algosdk.v2client.algod.AlgodClient,
        *,
        app_id: int = 0,
        signer: TransactionSigner | algokit_utils.Account | None = None,
        sender: str | None = None,
        suggested_params: algosdk.transaction.SuggestedParams | None = None,
        template_values: algokit_utils.TemplateValueMapping | None = None,
        app_name: str | None = None,
    ) -> None:
        ...

    @typing.overload
    def __init__(
        self,
        algod_client: algosdk.v2client.algod.AlgodClient,
        *,
        creator: str | algokit_utils.Account,
        indexer_client: algosdk.v2client.indexer.IndexerClient | None = None,
        existing_deployments: algokit_utils.AppLookup | None = None,
        signer: TransactionSigner | algokit_utils.Account | None = None,
        sender: str | None = None,
        suggested_params: algosdk.transaction.SuggestedParams | None = None,
        template_values: algokit_utils.TemplateValueMapping | None = None,
        app_name: str | None = None,
    ) -> None:
        ...

    def __init__(
        self,
        algod_client: algosdk.v2client.algod.AlgodClient,
        *,
        creator: str | algokit_utils.Account | None = None,
        indexer_client: algosdk.v2client.indexer.IndexerClient | None = None,
        existing_deployments: algokit_utils.AppLookup | None = None,
        app_id: int = 0,
        signer: TransactionSigner | algokit_utils.Account | None = None,
        sender: str | None = None,
        suggested_params: algosdk.transaction.SuggestedParams | None = None,
        template_values: algokit_utils.TemplateValueMapping | None = None,
        app_name: str | None = None,
    ) -> None:
        self.app_spec = APP_SPEC

        # calling full __init__ signature, so ignoring mypy warning about overloads
        self.app_client = algokit_utils.ApplicationClient(  # type: ignore[call-overload, misc]
            algod_client=algod_client,
            app_spec=self.app_spec,
            app_id=app_id,
            creator=creator,
            indexer_client=indexer_client,
            existing_deployments=existing_deployments,
            signer=signer,
            sender=sender,
            suggested_params=suggested_params,
            template_values=template_values,
            app_name=app_name,
        )"""
    )
    yield Part.Gap1
    yield Part.IncIndent
    yield forwarded_client_properties(context)
    yield Part.Gap1
    yield get_global_state_method(context)
    yield Part.Gap1
    yield get_local_state_method(context)
    yield Part.Gap1
    yield methods_by_side_effect(context, "none", context.methods.no_op)
    yield Part.Gap1
    yield methods_by_side_effect(context, "create", context.methods.create)
    yield Part.Gap1
    yield methods_by_side_effect(context, "update", context.methods.update_application)
    yield Part.Gap1
    yield methods_by_side_effect(context, "delete", context.methods.delete_application)
    yield Part.Gap1
    yield methods_by_side_effect(context, "opt_in", context.methods.opt_in)
    yield Part.Gap1
    yield methods_by_side_effect(context, "close_out", context.methods.close_out)
    yield Part.Gap1
    yield clear_method(context)
    yield Part.Gap1
    yield deploy_method(context)


def forwarded_client_properties(context: GenerateContext) -> DocumentParts:
    yield utils.indented(
        """
@property
def algod_client(self) -> algosdk.v2client.algod.AlgodClient:
    return self.app_client.algod_client

@property
def app_id(self) -> int:
    return self.app_client.app_id

@app_id.setter
def app_id(self, value: int) -> None:
    self.app_client.app_id = value

@property
def app_address(self) -> str:
    return self.app_client.app_address

@property
def sender(self) -> str | None:
    return self.app_client.sender

@sender.setter
def sender(self, value: str) -> None:
    self.app_client.sender = value

@property
def signer(self) -> TransactionSigner | None:
    return self.app_client.signer

@signer.setter
def signer(self, value: TransactionSigner) -> None:
    self.app_client.signer = value

@property
def suggested_params(self) -> algosdk.transaction.SuggestedParams | None:
    return self.app_client.suggested_params

@suggested_params.setter
def suggested_params(self, value: algosdk.transaction.SuggestedParams | None) -> None:
    self.app_client.suggested_params = value"""
    )


def embed_app_spec(context: GenerateContext) -> DocumentParts:
    yield Part.InlineMode
    yield '_APP_SPEC_JSON = r"""'
    yield context.app_spec.to_json()
    yield '"""'
    yield Part.RestoreLineMode
    yield "APP_SPEC = algokit_utils.ApplicationSpecification.from_json(_APP_SPEC_JSON)"


def signature(context: GenerateContext, name: str, method: ContractMethod) -> DocumentParts:
    yield f"def {name}("
    yield Part.IncIndent
    yield "self,"
    yield "*,"
    abi = method.abi
    if abi:
        for arg in abi.args:
            if arg.has_default:
                yield f"{arg.name}: {arg.python_type} | None = None,"
            else:
                yield f"{arg.name}: {arg.python_type},"
    if method.call_config == "create":
        yield on_complete_literals(method.on_complete)
        yield "transaction_parameters: algokit_utils.CreateTransactionParameters | None = None,"
    else:
        yield "transaction_parameters: algokit_utils.TransactionParameters | None = None,"
    yield Part.DecIndent
    if abi:
        yield f") -> algokit_utils.ABITransactionResponse[{abi.python_type}]:"
    else:
        yield ") -> algokit_utils.TransactionResponse:"
    # TODO: docstring


def instantiate_args(contract_method: ABIContractMethod | None) -> DocumentParts:
    if contract_method and not contract_method.args:
        yield f"args = {contract_method.args_class_name}()"
    elif contract_method:
        yield f"args = {contract_method.args_class_name}(", Part.IncIndent
        for arg in contract_method.args:
            yield f"{arg.name}={arg.name},"
        yield Part.DecIndent, ")"


def app_client_call(
    app_client_method: Literal["call", "create", "update", "delete", "opt_in", "close_out"],
    contract_method: ContractMethod,
) -> DocumentParts:
    yield f"result = self.app_client.{app_client_method}("
    yield Part.IncIndent
    if contract_method.abi:
        yield "call_abi_method=args.method(),"
    else:
        yield "call_abi_method=False,"
    if contract_method.call_config == "create":
        yield "transaction_parameters=_convert_create_transaction_parameters(transaction_parameters, on_complete),"
    elif "no_op" in contract_method.on_complete:
        yield "transaction_parameters=_convert_call_transaction_parameters(transaction_parameters),"
    else:
        yield "transaction_parameters=_convert_transaction_parameters(transaction_parameters),"
    if contract_method.abi:
        yield "**_as_dict(args, convert_all=True),"
    yield Part.DecIndent
    yield ")"
    if contract_method.abi and contract_method.abi.result_struct:
        yield 'elements = self.app_spec.hints[args.method()].structs["output"]["elements"]'
        yield "result_dict = {element[0]: value for element, value in zip(elements, result.return_value)}"
        yield f"result.return_value = {contract_method.abi.python_type}(**result_dict)"
    yield "return result"


def on_complete_literals(on_completes: Iterable[OnCompleteActionName]) -> DocumentParts:
    yield Part.InlineMode
    yield 'on_complete: typing.Literal["'
    yield utils.join('", "', on_completes)
    yield '"]'
    if "no_op" in on_completes:
        yield ' = "no_op"'
    yield ","
    yield Part.RestoreLineMode


def methods_by_side_effect(
    context: GenerateContext,
    side_effect: Literal["none", "create", "update", "delete", "opt_in", "close_out"],
    methods: list[ContractMethod],
) -> DocumentParts:
    if not methods:
        return

    for method in methods:
        contract_method = method.abi

        if side_effect == "none":
            if contract_method:  # an ABI method with no_op=CALL method
                full_method_name = contract_method.client_method_name
            else:
                full_method_name = "no_op"
        elif contract_method:  # an ABI method with a side effect
            full_method_name = f"{side_effect}_{contract_method.client_method_name}"
        else:  # a bare method
            full_method_name = f"{side_effect}_bare"
        yield signature(context, full_method_name, method)
        yield Part.IncIndent
        yield instantiate_args(contract_method)
        yield app_client_call("call" if side_effect == "none" else side_effect, method)
        yield Part.DecIndent
        yield Part.Gap1


def clear_method(context: GenerateContext) -> DocumentParts:
    yield utils.indented(
        """
def clear_state(
    self,
    transaction_parameters: algokit_utils.TransactionParameters | None = None,
    app_args: list[bytes] | None = None,
) -> algokit_utils.TransactionResponse:
    return self.app_client.clear_state(_convert_transaction_parameters(transaction_parameters), app_args)"""
    )


def deploy_method_args(context: GenerateContext, arg_name: str, methods: list[ContractMethod]) -> DocumentParts:
    yield Part.InlineMode
    has_bare = any(not m.abi for m in methods) or not methods
    typed_args = [m.abi.args_class_name for m in methods if m.abi]
    args = []
    if typed_args:
        deploy_type = "DeployCreate" if arg_name == "create_args" else "Deploy"
        args.append(f"{deploy_type}[{' | '.join(typed_args)}]")
    if has_bare:
        args.append("algokit_utils.DeployCallArgs")
        args.append("None")

    yield f"{arg_name}: "
    yield utils.join(" | ", args)
    if has_bare:
        yield " = None"
    yield ","
    yield Part.RestoreLineMode


def deploy_method(context: GenerateContext) -> DocumentParts:
    yield utils.indented(
        """
def deploy(
    self,
    version: str | None = None,
    *,
    signer: TransactionSigner | None = None,
    sender: str | None = None,
    allow_update: bool | None = None,
    allow_delete: bool | None = None,
    on_update: algokit_utils.OnUpdate = algokit_utils.OnUpdate.Fail,
    on_schema_break: algokit_utils.OnSchemaBreak = algokit_utils.OnSchemaBreak.Fail,
    template_values: algokit_utils.TemplateValueMapping | None = None,"""
    )
    yield Part.IncIndent
    yield deploy_method_args(context, "create_args", context.methods.create)
    yield deploy_method_args(context, "update_args", context.methods.update_application)
    yield deploy_method_args(context, "delete_args", context.methods.delete_application)
    yield Part.DecIndent
    yield utils.indented(
        """
) -> algokit_utils.DeployResponse:
    return self.app_client.deploy(
        version,
        signer=signer,
        sender=sender,
        allow_update=allow_update,
        allow_delete=allow_delete,
        on_update=on_update,
        on_schema_break=on_schema_break,
        template_values=template_values,
        create_args=_convert_deploy_args(create_args),
        update_args=_convert_deploy_args(update_args),
        delete_args=_convert_deploy_args(delete_args),
    )"""
    )


def get_global_state_method(context: GenerateContext) -> DocumentParts:
    if not context.app_spec.schema.get("global", {}).get("declared", {}):
        return
    yield "def get_global_state(self) -> GlobalState:"
    yield Part.IncIndent
    yield "state = typing.cast(dict[bytes, bytes | int], self.app_client.get_global_state(raw=True))"
    yield "return GlobalState(state)"
    yield Part.DecIndent


def get_local_state_method(context: GenerateContext) -> DocumentParts:
    if not context.app_spec.schema.get("local", {}).get("declared", {}):
        return
    yield "def get_local_state(self, account: str | None = None) -> LocalState:"
    yield Part.IncIndent
    yield "state = typing.cast(dict[bytes, bytes | int], self.app_client.get_local_state(account, raw=True))"
    yield "return LocalState(state)"
    yield Part.DecIndent


def generate(context: GenerateContext) -> DocumentParts:
    if context.disable_linting:
        yield disable_linting(context)
    yield generated_comment(context)
    yield imports(context)
    yield Part.Gap1
    yield embed_app_spec(context)
    yield helpers(context)
    yield Part.Gap2
    yield typed_arguments(context)
    yield Part.Gap2
    yield state_types(context)
    yield Part.Gap2
    yield typed_client(context)
