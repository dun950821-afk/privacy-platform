from app.services.observation_service import event_to_observation


def test_event_to_observation_maps_mobsf_tracker():
    observation = event_to_observation(
        event={"event_type": "static_tracker", "event_data": {"name": "Track", "url": "https://t"}},
        task_id=1, execution_id=2, engine_type="mobsf", engine_version="v4.5.4",
    )
    assert observation["observation_type"] == "security.tracker"
    assert observation["evidence_level"] == "observed"
    assert observation["engine_version"] == "v4.5.4"
    assert observation["schema_version"] == "1.0"


def test_event_to_observation_maps_permission():
    observation = event_to_observation(
        event={"event_type": "security_observation", "data_type": "permission", "api": "android.permission.READ_CONTACTS"},
        task_id=1, execution_id=2, engine_type="mobsf", engine_version="v4.5.4",
    )
    assert observation["observation_type"] == "security.permission"
    assert observation["subject"] == "android.permission.READ_CONTACTS"


def test_dataflow_event_is_marked_potential():
    observation = event_to_observation(
        event={"event_type": "static_data_flow", "data_type": "LOCATION", "event_data": {"rule": "location_to_network"}},
        task_id=1, execution_id=2, engine_type="appshark", engine_version="0.1.2",
    )
    assert observation["observation_type"] == "dataflow.privacy"
    assert observation["evidence_level"] == "potential"


def test_unknown_type_is_generic():
    observation = event_to_observation(
        event={"event_type": "static_url", "api": "https://x"},
        task_id=1, execution_id=2, engine_type="mobsf", engine_version="v4.5.4",
    )
    assert observation["observation_type"] == "security.endpoint"
    assert observation["evidence_level"] == "observed"
