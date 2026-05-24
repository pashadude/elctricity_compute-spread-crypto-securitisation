from services import scan_requests, worker


def test_worker_runs_queued_request_through_runtime(tmp_path, monkeypatch):
    calls = []

    def fake_run_once(args):
        calls.append(args)
        return 0

    monkeypatch.setattr(worker.runtime, "run_once", fake_run_once)
    request = scan_requests.enqueue_scan(source="api", force_signal=-2, logs=tmp_path)

    rc = worker.run_once(logs=tmp_path, scheduled=False)

    assert rc == 0
    assert calls
    assert calls[0].scan is True
    assert calls[0].dry_run is True
    assert calls[0].force_signal == -2.0
    assert scan_requests.requests_by_id(logs=tmp_path)[request["request_id"]]["status"] == "done"


def test_worker_respects_existing_lock(tmp_path):
    with scan_requests.scan_lock(logs=tmp_path) as acquired:
        assert acquired is True
        rc = worker.run_scan_request({"request_id": "locked", "source": "test"}, logs=tmp_path)

    assert rc == 75
