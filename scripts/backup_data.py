"""data/ 를 압축해 비공개 GitHub 저장소의 릴리스에 올리고, 다른 기기에서 내려받아 푼다.

실행:  python scripts/backup_data.py              ← 오늘 날짜로 올리기
       python scripts/backup_data.py --restore    ← 가장 최근 것을 내려받아 풀기 (data/ 가 있으면 --force 필요)
       python scripts/backup_data.py --list       ← 올라가 있는 사본 보기
gh(깃허브 명령줄 도구) 로그인이 필요하다. .env(키)는 넣지 않는다.
"""
import json
import subprocess
import sys
import tarfile
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config

# 원본 · 정제본 · 벡터. runs/(실행 기록)는 다시 만들 수 있어 넣지 않는다.
FOLDERS = ("data/raw", "data/processed", "data/index")


def _gh(*args: str) -> dict:
    # 왜: 실패해도 예외로 죽지 않고 사유를 돌려준다. gh 가 없거나 로그인이 안 된 경우도 같은 모양이다. 어디: 깃허브와 통하는 모든 곳.
    # 교안: 3일차 Part2 "에러도 결과로".
    try:
        p = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        return {"ok": False, "reason": "gh 가 설치돼 있지 않습니다 (brew install gh, gh auth login)"}
    if p.returncode != 0:
        return {"ok": False, "reason": p.stderr.strip() or p.stdout.strip()}
    return {"ok": True, "out": p.stdout.strip()}


def _assets() -> dict:
    r = _gh("release", "view", config.BACKUP_RELEASE_TAG, "--json", "assets")
    if not r["ok"]:
        return r
    names = sorted(a["name"] for a in json.loads(r["out"])["assets"])
    return {"ok": True, "assets": names}


def backup(today: str | None = None) -> dict:
    """성공: {"ok": True, "asset", "files", "mb"} / 실패: {"ok": False, "reason"}"""
    # 왜: 릴리스는 저장소의 공개 여부를 따른다. 공개 저장소에 올리면 관광공사 데이터를 재배포하는 것이 되므로 올리기 전에 코드가 막는다. 어디: 맨 앞.
    # 교안: 3일차 Part4 "안전장치는 코드에". PRD 11번 저작권 — 저장은 신청한 범위 안에서만 한다.
    vis = _gh("repo", "view", "--json", "visibility", "-q", ".visibility")
    if not vis["ok"]:
        return {"ok": False, "reason": f"저장소를 확인하지 못했습니다: {vis['reason']}"}
    if vis["out"] != "PRIVATE":
        return {"ok": False, "reason": f"저장소가 비공개가 아닙니다({vis['out']}). 올리지 않았습니다"}

    files = [p for folder in FOLDERS for p in sorted((ROOT / folder).rglob("*")) if p.is_file() and not p.name.endswith(".bak")]
    if not files:
        return {"ok": False, "reason": "올릴 파일이 없습니다 (data/ 가 비어 있음)"}

    # 왜: 날짜를 이름에 넣어 날마다 한 벌씩 남긴다. 잘못된 수집이 덮어써도 전날 것으로 돌아갈 수 있다. 어디: 압축 파일 이름.
    # 교안: 직접 대응 없음 (데이터 유실 대비). 수집에 열흘이 걸리는 데이터가 노트북 한 대에만 있던 것을 고친다.
    name = f"data-{today or date.today().isoformat()}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / name
        with tarfile.open(archive, "w:gz") as tar:
            for p in files:
                tar.add(p, arcname=str(p.relative_to(ROOT)))
        mb = round(archive.stat().st_size / 1e6, 1)

        if not _gh("release", "view", config.BACKUP_RELEASE_TAG)["ok"]:
            made = _gh("release", "create", config.BACKUP_RELEASE_TAG, "--title", "데이터 사본 (비공개)",
                       "--notes", "scripts/backup_data.py 가 올리는 data/ 사본. 코드 버전이 아니다.", "--latest=false")
            if not made["ok"]:
                return {"ok": False, "reason": f"릴리스를 만들지 못했습니다: {made['reason']}"}
        up = _gh("release", "upload", config.BACKUP_RELEASE_TAG, str(archive), "--clobber")   # 같은 날 다시 올리면 덮어쓴다
        if not up["ok"]:
            return {"ok": False, "reason": f"올리지 못했습니다: {up['reason']}"}
    return {"ok": True, "asset": name, "files": len(files), "mb": mb}


def restore(target: Path = ROOT, asset: str | None = None, force: bool = False) -> dict:
    """성공: {"ok": True, "asset", "files", "target"} / 실패: {"ok": False, "reason"}"""
    # 왜: 이미 있는 데이터를 말없이 덮어쓰면 오늘 받은 수집분을 잃는다. 어디: 풀기 전.
    # 교안: 3일차 Part4 "되돌릴 수 없는 일은 확인을 받는다" — 여기서는 --force 가 그 확인이다.
    if (target / "data" / "raw").exists() and any((target / "data" / "raw").iterdir()) and not force:
        return {"ok": False, "reason": f"{target / 'data'} 에 이미 데이터가 있습니다. 덮어쓰려면 --force 를 붙이세요"}
    listed = _assets()
    if not listed["ok"]:
        return {"ok": False, "reason": f"사본 목록을 읽지 못했습니다: {listed['reason']}"}
    if not listed["assets"]:
        return {"ok": False, "reason": "올라가 있는 사본이 없습니다"}
    asset = asset or listed["assets"][-1]   # 이름에 날짜가 있어 마지막이 가장 최근이다
    if asset not in listed["assets"]:
        return {"ok": False, "reason": f"{asset} 이 없습니다. 있는 것: {listed['assets']}"}

    with tempfile.TemporaryDirectory() as tmp:
        down = _gh("release", "download", config.BACKUP_RELEASE_TAG, "--pattern", asset, "--dir", tmp)
        if not down["ok"]:
            return {"ok": False, "reason": f"내려받지 못했습니다: {down['reason']}"}
        with tarfile.open(Path(tmp) / asset) as tar:
            members = tar.getmembers()
            tar.extractall(target, filter="data")   # 압축 파일 밖의 경로로 풀리는 것을 막는다
    return {"ok": True, "asset": asset, "files": sum(m.isfile() for m in members), "target": str(target)}


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--list" in args:
        result = _assets()
    elif "--restore" in args:
        names = [a for a in args if a.endswith(".tar.gz")]
        result = restore(asset=names[0] if names else None, force="--force" in args)
    else:
        result = backup()
    print(result)
    sys.exit(0 if result["ok"] else 1)
