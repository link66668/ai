# 服务层包初始化
# 使用延迟导入避免循环依赖

def __getattr__(name):
    """延迟导入——仅在访问时加载模块"""
    _imports = {
        'ai_service': '.ai_service',
        'AIService': '.ai_service',
        'SearchService': '.search_service',
        'DocumentParser': '.document_parser',
        'LightweightParser': '.document_parser',
        'LayoutAnalyzer': '.layout_analyzer',
        'TableExtractor': '.table_extractor',
        'ChunkingService': '.chunking_service',
        'embedding_service': '.embedding_service',
        'EmbeddingService': '.embedding_service',
        'vector_store': '.vector_store',
        'VectorStore': '.vector_store',
        'bm25_manager': '.bm25_manager',
        'BM25Manager': '.bm25_manager',
        'DocumentStructureExtractor': '.document_structure',
        'pipeline': '.async_pipeline',
        'AsyncPipeline': '.async_pipeline',
        'temp_file_manager': '.temp_file_service',
        'TempFileManager': '.temp_file_service',
        'RetrievalService': '.retrieval_service',
        'streaming_service': '.streaming_service',
        'StreamingService': '.streaming_service',
        'vision_service': '.vision_service',
        'VisionService': '.vision_service',
        'mineru_service': '.mineru_service',
        'MinerUService': '.mineru_service',
        'chat_engine': '.chat_engine',
        'ChatEngine': '.chat_engine',
    }

    if name in _imports:
        import importlib
        module = importlib.import_module(_imports[name], package=__package__)
        return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'ai_service', 'AIService',
    'SearchService',
    'DocumentParser', 'LightweightParser',
    'LayoutAnalyzer',
    'TableExtractor',
    'ChunkingService',
    'embedding_service', 'EmbeddingService',
    'vector_store', 'VectorStore',
    'bm25_manager', 'BM25Manager',
    'DocumentStructureExtractor',
    'pipeline', 'AsyncPipeline',
    'temp_file_manager', 'TempFileManager',
    'RetrievalService',
    'streaming_service', 'StreamingService',
    'vision_service', 'VisionService',
    'mineru_service', 'MinerUService',
]
