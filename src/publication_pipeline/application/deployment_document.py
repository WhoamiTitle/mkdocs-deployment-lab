"""Typed serialization contracts for deployment command results."""

from typing import NotRequired, TypedDict

from publication_pipeline.application.models import DeploymentReceipt, RsyncTransferMetrics


class RsyncTransferDocument(TypedDict):
    duration_seconds: float
    file_count: int
    transferred_file_count: int
    total_file_size_bytes: int
    transferred_file_size_bytes: int
    sent_bytes: int
    received_bytes: int


class DeploymentReceiptDocument(TypedDict):
    release_id: str
    location: str
    previous_release_id: str | None
    transfer: NotRequired[RsyncTransferDocument]


def rsync_transfer_to_document(transfer: RsyncTransferMetrics) -> RsyncTransferDocument:
    return RsyncTransferDocument(
        duration_seconds=transfer.duration_seconds,
        file_count=transfer.file_count,
        transferred_file_count=transfer.transferred_file_count,
        total_file_size_bytes=transfer.total_file_size_bytes,
        transferred_file_size_bytes=transfer.transferred_file_size_bytes,
        sent_bytes=transfer.sent_bytes,
        received_bytes=transfer.received_bytes,
    )


def deployment_receipt_to_document(receipt: DeploymentReceipt) -> DeploymentReceiptDocument:
    document = DeploymentReceiptDocument(
        release_id=receipt.release_id.value,
        location=receipt.location,
        previous_release_id=(
            receipt.previous_release_id.value if receipt.previous_release_id is not None else None
        ),
    )
    if receipt.transfer is not None:
        document["transfer"] = rsync_transfer_to_document(receipt.transfer)
    return document
