from opendataframework.view import (
    AudioView,
    DataViewProtocol,
    DocumentView,
    ImageView,
    LocationView,
    ReplayProtocol,
    StreamingAudioView,
    StreamingVideoView,
    TableView,
    TimeseriesView,
    VideoView,
)


def test_data_view_protocol_detects_data_view_method():
    class Viewed:
        def data_view(self):
            return TableView()

    assert isinstance(Viewed(), DataViewProtocol)


def test_data_view_protocol_rejects_repository_without_data_view():
    class Unviewed:
        def all(self):
            return []

    assert not isinstance(Unviewed(), DataViewProtocol)


def test_table_view_defaults_to_every_field():
    assert TableView().fields is None


def test_table_view_can_override_fields():
    assert TableView(fields=("id", "name")).fields == ("id", "name")


def test_image_view_holds_a_single_field():
    assert ImageView(field="data").field == "data"


def test_video_view_holds_a_single_field():
    assert VideoView(field="clip").field == "clip"


def test_streaming_video_view_holds_a_single_field():
    assert StreamingVideoView(field="data").field == "data"


def test_audio_view_holds_a_single_field():
    assert AudioView(field="clip").field == "clip"


def test_streaming_audio_view_holds_a_single_field():
    assert StreamingAudioView(field="chunk").field == "chunk"


def test_document_view_holds_a_single_field():
    assert DocumentView(field="payload").field == "payload"


def test_location_view_holds_a_lat_lon_pair():
    assert LocationView(fields=("lat", "lon")).fields == ("lat", "lon")


def test_timeseries_view_holds_a_single_field():
    assert TimeseriesView(field="timestamp").field == "timestamp"


def test_replay_protocol_detects_replay_field_method():
    class Replayed:
        def replay_field(self):
            return "recorded_at"

    assert isinstance(Replayed(), ReplayProtocol)


def test_replay_protocol_rejects_repository_without_replay_field():
    class NotReplayed:
        def all(self):
            return []

    assert not isinstance(NotReplayed(), ReplayProtocol)
