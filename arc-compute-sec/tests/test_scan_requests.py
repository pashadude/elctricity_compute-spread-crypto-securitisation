from services import scan_requests


def test_enqueue_live_request_is_gated_by_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_CHAIN", raising=False)

    request = scan_requests.enqueue_scan(source="api", live=True, logs=tmp_path)

    assert request["requested_live"] is True
    assert request["live"] is False
    assert scan_requests.pending_requests(logs=tmp_path)[0]["request_id"] == request["request_id"]


def test_scan_lock_blocks_overlap(tmp_path):
    with scan_requests.scan_lock(logs=tmp_path) as first:
        assert first is True
        with scan_requests.scan_lock(logs=tmp_path) as second:
            assert second is False


def test_mark_request_removes_from_pending(tmp_path):
    request = scan_requests.enqueue_scan(source="api", logs=tmp_path)

    scan_requests.mark_request(request["request_id"], "done", logs=tmp_path, return_code=0)

    assert scan_requests.pending_requests(logs=tmp_path) == []


def test_scan_lock_recovers_dead_owner(tmp_path, monkeypatch):
    lock = tmp_path / scan_requests.LOCK_NAME
    lock.write_text('{"ts": 9999999999, "pid": 1, "pid_start_ticks": "old"}')
    monkeypatch.setattr(scan_requests, "_pid_start_ticks", lambda pid: "new")

    with scan_requests.scan_lock(logs=tmp_path) as acquired:
        assert acquired is True


def test_scan_lock_recovers_legacy_lock_when_procfs_available(tmp_path, monkeypatch):
    lock = tmp_path / scan_requests.LOCK_NAME
    lock.write_text('{"ts": 9999999999, "pid": 1}')
    monkeypatch.setattr(scan_requests, "_pid_start_ticks", lambda pid: "current")

    with scan_requests.scan_lock(logs=tmp_path) as acquired:
        assert acquired is True
