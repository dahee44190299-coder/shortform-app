"""whitelist.py 단위 테스트 — Founder + 초대 코드 시스템."""
import pytest

import whitelist


@pytest.fixture
def isolated_whitelist(tmp_path, monkeypatch):
    """각 테스트가 별도 임시 파일."""
    fake = tmp_path / "shortform_projects" / "_whitelist.json"
    fake_founders = tmp_path / "shortform_projects" / "_founders.json"
    monkeypatch.setattr(whitelist, "WHITELIST_PATH", str(fake))
    monkeypatch.setattr(whitelist, "FOUNDERS_PATH", str(fake_founders))
    # DEFAULT_FOUNDER 폴백 비활성 (테스트 격리)
    monkeypatch.setattr(whitelist, "DEFAULT_FOUNDER", "")
    yield fake


@pytest.fixture
def founder_set(monkeypatch):
    """Founder ID 환경변수 설정."""
    monkeypatch.setenv("FOUNDER_USER_IDS", "founder@me.com,partner@me.com")
    # api_keys.get_api_key를 환경변수만 보도록
    monkeypatch.setattr(whitelist.api_keys, "get_api_key",
                        lambda name: "founder@me.com,partner@me.com"
                                     if name == "FOUNDER_USER_IDS" else "")
    yield


# ── Founder ─────────────────────────────────────────────────────

class TestFounder:
    def test_founder_is_pro(self, isolated_whitelist, founder_set):
        assert whitelist.is_founder("founder@me.com") is True
        assert whitelist.is_pro_user("founder@me.com") is True
        assert whitelist.user_tier("founder@me.com") == "founder"

    def test_non_founder(self, isolated_whitelist, founder_set):
        assert whitelist.is_founder("random@user.com") is False

    def test_empty_id(self, isolated_whitelist, founder_set):
        assert whitelist.is_founder("") is False
        assert whitelist.is_pro_user("") is False
        assert whitelist.user_tier("") == "free"


# ── 초대 코드 ─────────────────────────────────────────────────

class TestInviteCode:
    def test_generate_code_format(self, isolated_whitelist):
        code = whitelist.generate_invite_code(note="테스트")
        assert code.startswith("INV-")
        assert len(code) == 13  # INV-XXXX-XXXX

    def test_redeem_makes_invitee(self, isolated_whitelist):
        code = whitelist.generate_invite_code()
        result = whitelist.redeem_invite_code(code, "user1")
        assert result["ok"] is True
        assert whitelist.is_invitee("user1") is True
        assert whitelist.is_pro_user("user1") is True
        assert whitelist.user_tier("user1") == "invitee"

    def test_redeem_invalid_code(self, isolated_whitelist):
        r = whitelist.redeem_invite_code("INV-WRONG-CODE", "user1")
        assert r["ok"] is False

    def test_redeem_empty_inputs(self, isolated_whitelist):
        assert whitelist.redeem_invite_code("", "user")["ok"] is False
        assert whitelist.redeem_invite_code("INV-X-X", "")["ok"] is False

    def test_max_uses_default_1(self, isolated_whitelist):
        code = whitelist.generate_invite_code(max_uses=1)
        r1 = whitelist.redeem_invite_code(code, "u1")
        r2 = whitelist.redeem_invite_code(code, "u2")
        assert r1["ok"] is True
        assert r2["ok"] is False
        assert "초과" in r2["reason"]

    def test_max_uses_n(self, isolated_whitelist):
        code = whitelist.generate_invite_code(max_uses=3)
        for u in ("a", "b", "c"):
            assert whitelist.redeem_invite_code(code, u)["ok"] is True
        assert whitelist.redeem_invite_code(code, "d")["ok"] is False

    def test_same_user_cannot_redeem_twice(self, isolated_whitelist):
        code = whitelist.generate_invite_code(max_uses=5)
        whitelist.redeem_invite_code(code, "u1")
        r2 = whitelist.redeem_invite_code(code, "u1")
        assert r2["ok"] is False
        assert "이미" in r2["reason"]


# ── List + Revoke ─────────────────────────────────────────────

class TestListAndRevoke:
    def test_list_codes_after_generate(self, isolated_whitelist):
        whitelist.generate_invite_code(note="첫번째")
        whitelist.generate_invite_code(note="두번째")
        codes = whitelist.list_invite_codes()
        assert len(codes) == 2
        assert {"첫번째", "두번째"} == {c["note"] for c in codes}

    def test_list_invitees(self, isolated_whitelist):
        c = whitelist.generate_invite_code(max_uses=2)
        whitelist.redeem_invite_code(c, "u1")
        whitelist.redeem_invite_code(c, "u2")
        invitees = whitelist.list_invitees()
        assert {"u1", "u2"} == {i["user_id"] for i in invitees}

    def test_revoke_invitee(self, isolated_whitelist):
        c = whitelist.generate_invite_code()
        whitelist.redeem_invite_code(c, "u1")
        assert whitelist.is_invitee("u1") is True
        assert whitelist.revoke_invitee("u1") is True
        assert whitelist.is_invitee("u1") is False
        # 재호출은 False
        assert whitelist.revoke_invitee("u1") is False


# ── 통합: is_pro_user with paid ──────────────────────────────

class TestIsProUser:
    def test_paid_user_is_pro(self, isolated_whitelist):
        paid = {"paid_user@x.com"}
        assert whitelist.is_pro_user("paid_user@x.com", paid) is True

    def test_unknown_user_not_pro(self, isolated_whitelist):
        assert whitelist.is_pro_user("nobody@x.com", set()) is False
        assert whitelist.user_tier("nobody@x.com") == "free"

    def test_priority_order(self, isolated_whitelist, founder_set):
        # founder는 paid 목록에 없어도 founder 티어
        assert whitelist.user_tier("founder@me.com", set()) == "founder"
        # 같은 사람이 paid에도 있으면 founder가 우선
        assert whitelist.user_tier("founder@me.com", {"founder@me.com"}) == "founder"


# ── UI 등록 + first user claim (Phase 4 admin) ───────────────

class TestAddRemoveFounder:
    def test_add_founder(self, isolated_whitelist):
        r = whitelist.add_founder("new@founder.com", added_by="ui",
                                    note="테스트")
        assert r["ok"] is True
        assert whitelist.is_founder("new@founder.com") is True
        # 중복 추가 방지
        r2 = whitelist.add_founder("new@founder.com")
        assert r2["ok"] is False

    def test_remove_founder(self, isolated_whitelist):
        whitelist.add_founder("f1@x.com")
        whitelist.add_founder("f2@x.com")
        assert whitelist.remove_founder("f1@x.com") is True
        assert whitelist.is_founder("f1@x.com") is False

    def test_cannot_remove_last_founder(self, isolated_whitelist):
        # 마지막 founder 보호 (시스템 잠금 방지)
        whitelist.add_founder("only@founder.com")
        assert whitelist.remove_founder("only@founder.com") is False
        assert whitelist.is_founder("only@founder.com") is True

    def test_remove_nonexistent(self, isolated_whitelist):
        assert whitelist.remove_founder("nobody@x.com") is False


class TestClaimFirstFounder:
    def test_claim_when_empty(self, isolated_whitelist):
        r = whitelist.claim_first_founder("first@user.com")
        assert r["ok"] is True
        assert whitelist.is_founder("first@user.com") is True

    def test_no_claim_if_founder_exists(self, isolated_whitelist):
        whitelist.add_founder("existing@x.com")
        r = whitelist.claim_first_founder("second@user.com")
        assert r["ok"] is False
        assert whitelist.is_founder("second@user.com") is False

    def test_no_claim_with_empty_id(self, isolated_whitelist):
        r = whitelist.claim_first_founder("")
        assert r["ok"] is False

    def test_disabled_via_flag(self, isolated_whitelist, monkeypatch):
        monkeypatch.setattr(whitelist, "ALLOW_FIRST_USER_CLAIM", False)
        r = whitelist.claim_first_founder("first@user.com")
        assert r["ok"] is False


class TestListFounders:
    def test_list_includes_file_founders(self, isolated_whitelist):
        whitelist.add_founder("a@x.com", note="첫번째")
        whitelist.add_founder("b@x.com", note="두번째")
        founders = whitelist.list_founders()
        emails = {f["user_id"] for f in founders}
        assert {"a@x.com", "b@x.com"}.issubset(emails)
        # source 필드
        for f in founders:
            assert "source" in f
