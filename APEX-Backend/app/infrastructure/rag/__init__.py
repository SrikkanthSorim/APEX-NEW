"""Retrieval-Augmented Generation building blocks for the Strategy chatbot.

Turns a repository's discovery report into semantic knowledge chunks, embeds
them, stores them in an embedded Qdrant vector store, and retrieves the most
relevant chunks for a user question. Kept free of any HTTP/LLM concerns.
"""
