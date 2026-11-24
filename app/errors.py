from flask import jsonify


MESSAGES = {
    "EMPTY_FILE": "文件为空",
    "BLANK_FILE": "文件只有空白",
    "HEADER_ONLY": "文件只有表头",
    "HEADER_MISMATCH": "表头与本项目字段不一致",
    "UNCLOSED_QUOTE": "引号未闭合，文件已拒收",
    "TOO_MANY_ROWS": "数据行超过上限",
    "FILE_TOO_LARGE": "文件超过大小上限",
    "KEY_MISSING": "主键为空",
    "CONFLICT_DUPLICATE": "同一键存在冲突内容",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "阶段不存在",
    "RUN_NOT_FOUND": "批次不存在",
    "STALE_REVIEW": "批次已被更新，请刷新后复核",
    "GATE_BLOCKED": "存在阻断项，不能签发",
    "NOT_APPROVED": "批次尚未签发",
    "NOT_REVIEWED": "标本尚未复核，不能签发确认凭据",
    "REVIEW_SUPERSEDED": "标本已更正，原复核失效，请重新复核",
    "CREDENTIAL_SEALED": "确认凭据已签发留存，不能再修改或重复签发",
    "CREDENTIAL_NOT_FOUND": "确认凭据不存在",
    "SPECIMEN_NOT_FOUND": "标本不在该批次中",
    "SPECIMEN_INVALID": "更正后的标本未通过整理校验",
    "SPECIMEN_KEY_MISMATCH": "更正不能改变标本编号",
    "BAD_REQUEST": "请求内容不完整",
}


class DomainIssue(Exception):
    def __init__(self, code: str, status: int = 400, detail: str | None = None):
        self.code = code
        self.status = status
        self.detail = detail
        super().__init__(code)


def error_response(exc: DomainIssue):
    return jsonify(error=exc.detail or MESSAGES.get(exc.code, "请求无法处理"), code=exc.code), exc.status
