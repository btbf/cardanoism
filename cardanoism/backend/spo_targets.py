"""spo_targets.py
SPO 投票対象 GA の判定 (CIP-1694 + Plomin HF 準拠)。

GA タイプごとに SPO が投票可能かを返す。ParameterChange の場合は
security group に該当するパラメータが含まれているかをチェックする。
"""
from __future__ import annotations

from typing import Any


# CIP-1694 + Plomin HF で security group とされるプロトコルパラメータ。
# 命名は Cardano CDDL の snake_case と camelCase の両方を網羅 (Koios / Ogmios の差異吸収)。
_SECURITY_GROUP_PARAMS: set[str] = {
    # ブロック / トランザクションサイズ
    "max_block_size",        "maxBlockBodySize",
    "max_tx_size",           "maxTransactionSize",
    "max_block_header_size", "maxBlockHeaderSize",
    "max_value_size",        "maxValueSize",
    # 実行ユニット
    "max_block_execution_units", "maxBlockExecutionUnits",
    "max_tx_execution_units",    "maxExecutionUnitsPerTransaction",
    "max_collateral_inputs",     "maxCollateralInputs",
    # 手数料
    "min_fee_a",                 "minFeeCoefficient",
    "min_fee_b",                 "minFeeConstant",
    "coins_per_utxo_byte",       "minUtxoDepositCoefficient", "utxoCostPerByte",
    # ガバナンス
    "gov_action_deposit",        "governanceActionDeposit",
    # Plomin HF 後 (refScript 関連)
    "min_fee_ref_script_cost_per_byte", "minFeeReferenceScripts",
    "ref_script_cost_stride",           "minFeeReferenceScriptsRange",
    "ref_script_cost_multiplier",       "minFeeReferenceScriptsMultiplier",
}


# 無条件で SPO 対象 (CIP-1694)
_UNCONDITIONAL_SPO_TYPES = {
    "HardForkInitiation",
    "NoConfidence",
    "UpdateCommittee",
    "InfoAction",  # 任意 (意見表明)
}

# SPO 対象外 (CIP-1694)
_NON_SPO_TYPES = {
    "TreasuryWithdrawals",
    "NewConstitution",
}


def _walk_keys(obj: Any) -> set[str]:
    """ネストした dict / list 構造から全 key を再帰的に収集する。"""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                keys.add(k)
            keys.update(_walk_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            keys.update(_walk_keys(item))
    return keys


def is_security_group_param_change(action_obj: Any) -> bool:
    """ParameterChange 系オブジェクトが security group のパラメータ変更を含むか。

    Koios `proposed_action` / Ogmios action.parameters の両方の構造に対応。
    """
    if not action_obj:
        return False
    keys = _walk_keys(action_obj)
    return bool(keys & _SECURITY_GROUP_PARAMS)


def compute_spo_target(proposal_type: str, action_obj: Any = None) -> int:
    """proposal_type と action データから SPO 投票対象かを判定して 0/1 を返す。

    Args:
        proposal_type: "HardForkInitiation" / "ParameterChange" / etc.
        action_obj   : ParameterChange の場合の proposed_action / Ogmios action 全体。
                       他のタイプでは無視される。

    Returns: 1 = SPO 対象 / 0 = 対象外
    """
    pt = (proposal_type or "").strip()
    if pt in _UNCONDITIONAL_SPO_TYPES:
        return 1
    if pt in _NON_SPO_TYPES:
        return 0
    if pt == "ParameterChange":
        return 1 if is_security_group_param_change(action_obj) else 0
    return 0
