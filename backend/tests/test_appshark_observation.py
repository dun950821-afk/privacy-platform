from app.services.appshark_observation import appshark_observations

RAW = {
    "ComplianceInfo": {
        "PRIVACY": {
            "device_id_to_network": {
                "level": "high",
                "vulners": [
                    {"details": {"Source": ["getDeviceId"], "Sink": ["okhttp3.Request"], "path": ["a", "b"]}}
                ],
            }
        }
    }
}


def test_appshark_observations_are_potential_not_confirmed():
    observations = appshark_observations(RAW, task_id=1, execution_id=2)
    assert len(observations) == 1
    assert observations[0]["observation_type"] == "dataflow.privacy"
    assert observations[0]["evidence_level"] == "potential"
    assert observations[0]["rule_id"] == "device_id_to_network"


def test_appshark_observations_skip_entries_without_source_or_sink():
    raw = {"SecurityInfo": {"SEC": {"rule": {"vulners": [{"details": {"position": "x"}}]}}}}
    assert appshark_observations(raw, task_id=1, execution_id=2) == []
