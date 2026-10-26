"""Pipelines package marker."""
from voxclone.pipelines.text_pipeline import run_text_pipeline
from voxclone.pipelines.text_splitter import split_text_into_chunks

__all__ = ["run_text_pipeline", "split_text_into_chunks"]
