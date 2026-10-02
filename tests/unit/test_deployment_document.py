from publication_pipeline.application.deployment_document import deployment_receipt_to_document
from publication_pipeline.application.models import DeploymentReceipt, RsyncTransferMetrics


def test_deployment_document_omits_absent_transfer() -> None:
    document = deployment_receipt_to_document(
        DeploymentReceipt(
            release_id="abcdef123456-20261002T010203Z",
            location="public_html/site",
        )
    )

    assert document == {
        "release_id": "abcdef123456-20261002T010203Z",
        "location": "public_html/site",
        "previous_release_id": None,
    }


def test_deployment_document_contains_typed_transfer_metrics() -> None:
    transfer = RsyncTransferMetrics(
        duration_seconds=0.25,
        file_count=10,
        transferred_file_count=8,
        total_file_size_bytes=1000,
        transferred_file_size_bytes=800,
        sent_bytes=400,
        received_bytes=40,
    )

    document = deployment_receipt_to_document(
        DeploymentReceipt(
            release_id="abcdef123456-20261002T010203Z",
            location="public_html/site",
            previous_release_id="previous-release",
            transfer=transfer,
        )
    )

    assert document["transfer"] == {
        "duration_seconds": 0.25,
        "file_count": 10,
        "transferred_file_count": 8,
        "total_file_size_bytes": 1000,
        "transferred_file_size_bytes": 800,
        "sent_bytes": 400,
        "received_bytes": 40,
    }
