from dataclasses import dataclass

from opendataframework.entity import Entity
from opendataframework.repository import Repository
from opendataframework.view import (
    AudioView,
    ContentMetadata,
    ContentMetadataProtocol,
    Conversation,
    ConversationProtocol,
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


def test_timeseries_view_defaults_to_every_field_in_one_line():
    view = TimeseriesView(field="timestamp")

    assert view.fields is None
    assert view.group is None


def test_timeseries_view_can_select_fields():
    view = TimeseriesView(field="step", fields=("loss", "accuracy"))

    assert view.fields == ("loss", "accuracy")


def test_timeseries_view_can_group_records():
    assert TimeseriesView(field="step", group="run_id").group == "run_id"


def test_replay_protocol_detects_field_method():
    class Replayed:
        def field(self):
            return "recorded_at"

    assert isinstance(Replayed(), ReplayProtocol)


def test_replay_protocol_rejects_repository_without_field():
    class NotReplayed:
        def all(self):
            return []

    assert not isinstance(NotReplayed(), ReplayProtocol)


def test_content_metadata_defaults_to_nothing_declared():
    metadata = ContentMetadata()

    assert metadata.filename is None
    assert metadata.content_type is None


def test_content_metadata_holds_filename_and_content_type():
    metadata = ContentMetadata(filename="report.pdf", content_type="application/pdf")

    assert metadata.filename == "report.pdf"
    assert metadata.content_type == "application/pdf"


def test_content_metadata_protocol_detects_content_metadata_method():
    class Described:
        def content_metadata(self, entity):
            return ContentMetadata()

    assert isinstance(Described(), ContentMetadataProtocol)


def test_content_metadata_protocol_rejects_repository_without_content_metadata():
    class Undescribed:
        def data_view(self):
            return ImageView(field="data")

    assert not isinstance(Undescribed(), ContentMetadataProtocol)


def test_content_metadata_can_be_derived_without_entity_fields():
    @dataclass
    class Photo:
        id: int
        data: bytes

    class Photos:
        def content_metadata(self, photo):
            return ContentMetadata(filename=f"{photo.id}.png", content_type="image/png")

    assert Photos().content_metadata(Photo(id=7, data=b"")) == ContentMetadata(
        filename="7.png", content_type="image/png"
    )


def test_conversation_defaults_to_cards_with_no_sender():
    conversation = Conversation(
        channel="restaurants", thread="restaurant", time="created_at", text="body"
    )

    assert conversation.direction is None
    assert conversation.sender is None


def test_conversation_holds_message_fields():
    conversation = Conversation(
        channel="restaurants",
        thread="restaurant",
        time="received_at",
        text="text",
        direction="direction",
        sender="sender",
    )

    assert conversation.direction == "direction"
    assert conversation.sender == "sender"


def test_conversation_protocol_holds_beside_data_view_protocol():
    @Entity
    @dataclass
    class Message:
        id: int
        restaurant: str
        received_at: str
        text: str

    @Repository(Message)
    class Messages:
        def all(self):
            return []

        def data_view(self):
            return TableView()

        def conversation(self):
            return Conversation(
                channel="restaurants", thread="restaurant", time="received_at", text="text"
            )

    messages = Messages()

    assert isinstance(messages, DataViewProtocol)
    assert isinstance(messages, ConversationProtocol)


def test_conversation_protocol_rejects_repository_without_conversation():
    class Unthreaded:
        def data_view(self):
            return TableView()

    assert not isinstance(Unthreaded(), ConversationProtocol)
