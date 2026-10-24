"""Run: python scripts/openminion_research.py --request examples/organization-research.json"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.openminion_research import OrganizationResearchRequest, run_research


class CortensorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTENSOR_", env_file=".env", extra="ignore")
    api_url: str = Field(min_length=1)
    api_key: str = ""
    model: str = "gpt-oss-20b"
    session_id: int = Field(default=1, ge=1)
    api_mode: Literal["auto", "openai_chat", "cortensor_completion"] = "auto"


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenMinion组织研究：公开来源采集、报告与原文核验")
    parser.add_argument("--request", type=Path, required=True, help="结构化研究JSON")
    parser.add_argument("--output", type=Path, required=True, help="新的结果目录，禁止覆盖")
    parser.add_argument("--provider", choices=["configured", "cortensor"], default="configured")
    args = parser.parse_args()
    request = OrganizationResearchRequest.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    config = None
    if args.provider == "cortensor":
        try:
            configured = CortensorSettings()
        except ValidationError:
            parser.error("Cortensor配置不完整或无效；检查CORTENSOR_API_URL、MODEL、SESSION_ID和API_MODE")
        if "api.cortensor.app" in configured.api_url and not configured.api_key:
            parser.error("Cortensor Portal需要独立的CORTENSOR_API_KEY；日常模型密钥不能替代")
        config = {"provider": "cortensor", "model": configured.model,
                  "api_base": configured.api_url, "api_key": configured.api_key,
                  "session_id": configured.session_id, "api_mode": configured.api_mode}
    args.output.mkdir(parents=True, exist_ok=False)
    print(json.dumps({"status": "running", "scope": request.model_dump(), "plan": [
        "检索各对象原始来源", "读取并保存原文证据", "综合研究方向及缺口", "核对最终主张和引用"]}, ensure_ascii=False), flush=True)
    def progress(entry):
        print(json.dumps({key: entry[key] for key in ("stage", "reason", "issues", "tool", "arguments", "status", "error", "result_count", "evidence_id", "document_format", "linked_paper")
                          if key in entry}, ensure_ascii=False), flush=True)

    result = run_research(request, model_config=config, on_event=progress)
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "report.md").write_text(result["report"], encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()),
                      "evidence_count": len(result["evidence"]), "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
