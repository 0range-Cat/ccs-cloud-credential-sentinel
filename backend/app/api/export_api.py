from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..db import get_session
from .. import services

router = APIRouter()


def _filters(platform: str | None, type: str | None, review: str | None, verify: str | None) -> dict:
    return {k: v for k, v in {
        "platform": platform, "type": type, "review": review, "verify": verify,
    }.items() if v}


@router.get("/export/findings.csv")
def export_csv(
    session: Session = Depends(get_session),
    masked: bool = True,
    platform: str | None = None,
    type: str | None = None,
    review: str | None = None,
    verify: str | None = None,
):
    rows = services.iter_export_rows(session, masked, _filters(platform, type, review, verify))

    def gen():
        # 首块表头，随后流式输出，避免大导出阻塞内存
        yield services.EXPORT_FIELDS[0]
        for name in services.EXPORT_FIELDS[1:]:
            yield "," + name
        yield "\r\n"
        import csv as _csv
        import io as _io
        buf = _io.StringIO()
        writer = _csv.writer(buf)
        for row in rows:
            writer.writerow([services.csv_escape_cell(row.get(f)) for f in services.EXPORT_FIELDS])
            data = buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
            yield data

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=findings.csv"})


@router.get("/export/findings.json")
def export_json(
    session: Session = Depends(get_session),
    masked: bool = True,
    platform: str | None = None,
    type: str | None = None,
    review: str | None = None,
    verify: str | None = None,
):
    rows = services.iter_export_rows(session, masked, _filters(platform, type, review, verify))

    def gen():
        yield "["
        first = True
        import json as _json
        for row in rows:
            piece = _json.dumps(row, ensure_ascii=False, default=str)
            yield ("" if first else ",") + piece
            first = False
        yield "]"

    return StreamingResponse(gen(), media_type="application/json; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=findings.json"})
