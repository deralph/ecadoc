import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import types


# Minimal stubs for optional third-party SDKs used during testing
if "stripe" not in sys.modules:
    class _StripeStub:
        def __init__(self):
            self.api_key = None
            self.checkout = types.SimpleNamespace(Session=types.SimpleNamespace(create=lambda **_: None))
            self.billing_portal = types.SimpleNamespace(Session=types.SimpleNamespace(create=lambda **_: None))
            self.Subscription = types.SimpleNamespace(retrieve=lambda *_: {})
            self.Webhook = types.SimpleNamespace(construct_event=lambda *_: {})

    sys.modules["stripe"] = _StripeStub()

if "boto3" not in sys.modules:
    def _client(*args, **kwargs):  # noqa: D401
        class _S3Stub:
            def put_object(self, **kwargs):
                return {"ETag": "stub"}

        return _S3Stub()

    sys.modules["boto3"] = types.SimpleNamespace(client=_client)

if "botocore" not in sys.modules:
    botocore_module = types.ModuleType("botocore")
    botocore_exceptions = types.SimpleNamespace(BotoCoreError=Exception, ClientError=Exception)
    sys.modules["botocore"] = botocore_module
    sys.modules["botocore.exceptions"] = botocore_exceptions

if "langchain" not in sys.modules:
    langchain_module = types.ModuleType("langchain")
    text_splitter_module = types.ModuleType("langchain.text_splitter")

    class RecursiveCharacterTextSplitter:
        def __init__(self, **kwargs):
            pass

        def split_text(self, text):
            return [text]

    text_splitter_module.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter
    sys.modules["langchain"] = langchain_module
    sys.modules["langchain.text_splitter"] = text_splitter_module

if "langchain_openai" not in sys.modules:
    class _Embeddings:
        def __init__(self, **kwargs):
            pass

    class _Chat:
        def __init__(self, **kwargs):
            pass

        def invoke(self, *_args, **_kwargs):
            return {}

    sys.modules["langchain_openai"] = types.SimpleNamespace(OpenAIEmbeddings=_Embeddings, ChatOpenAI=_Chat)
else:
    module = sys.modules["langchain_openai"]
    if not hasattr(module, "ChatOpenAI"):
        class _Chat:
            def __init__(self, **kwargs):
                pass

            def invoke(self, *_args, **_kwargs):
                return {}

        module.ChatOpenAI = _Chat

if "langchain_community.vectorstores" not in sys.modules:
    class _FAISS:
        @classmethod
        def from_documents(cls, docs, embeddings):
            return cls()

        def save_local(self, path):
            return None

    sys.modules["langchain_community"] = types.ModuleType("langchain_community")
    sys.modules["langchain_community.vectorstores"] = types.SimpleNamespace(FAISS=_FAISS)

if "langchain.docstore.document" not in sys.modules:
    class _Document:
        def __init__(self, page_content, metadata=None):
            self.page_content = page_content
            self.metadata = metadata or {}

    sys.modules["langchain.docstore"] = types.ModuleType("langchain.docstore")
    sys.modules["langchain.docstore.document"] = types.SimpleNamespace(Document=_Document)

if "langchain.agents" not in sys.modules:
    agents_module = types.ModuleType("langchain.agents")

    def _create_tool_calling_agent(*args, **kwargs):
        return object()

    class _AgentExecutor:
        def __init__(self, **kwargs):
            pass

        def invoke(self, *_args, **_kwargs):
            return {}

    agents_module.create_tool_calling_agent = _create_tool_calling_agent
    agents_module.AgentExecutor = _AgentExecutor
    sys.modules["langchain.agents"] = agents_module

if "langchain_core.tools" not in sys.modules:
    sys.modules["langchain_core"] = types.ModuleType("langchain_core")

    def _tool(fn):
        return fn

    sys.modules["langchain_core.tools"] = types.SimpleNamespace(tool=_tool)

if "langchain_core.messages" not in sys.modules:
    class _HumanMessage:
        def __init__(self, content):
            self.content = content

    sys.modules["langchain_core.messages"] = types.SimpleNamespace(HumanMessage=_HumanMessage)

if "langchain_tavily" not in sys.modules:
    class _TavilySearch:
        def __init__(self, **kwargs):
            pass

        def invoke(self, *_args, **_kwargs):
            return {}

    sys.modules["langchain_tavily"] = types.SimpleNamespace(TavilySearch=_TavilySearch)

if "inference_sdk" not in sys.modules:
    class _InferenceHTTPClient:
        def __init__(self, **kwargs):
            pass

        def inference(self, *_args, **_kwargs):
            return {}

    sys.modules["inference_sdk"] = types.SimpleNamespace(InferenceHTTPClient=_InferenceHTTPClient)

if "tiktoken" not in sys.modules:
    class _Encoding:
        def __init__(self, name):
            self.name = name

        def encode(self, text):
            return [0]

        def decode(self, tokens):
            return ""

    def _encoding_for_model(model_name):
        return _Encoding(model_name)

    sys.modules["tiktoken"] = types.SimpleNamespace(encoding_for_model=_encoding_for_model)

if "modules.agent" not in sys.modules:
    agent_package = types.ModuleType("modules.agent")
    sys.modules["modules.agent"] = agent_package

if "modules.agent.workflow" not in sys.modules:
    workflow_module = types.ModuleType("modules.agent.workflow")

    class _AgentWorkflowStub:
        @staticmethod
        def get_or_create_chat_session():
            return "stub-session"

    workflow_module.agent_workflow = _AgentWorkflowStub()
    sys.modules["modules.agent.workflow"] = workflow_module
    agent_pkg = sys.modules.setdefault("modules.agent", types.ModuleType("modules.agent"))
    agent_pkg.workflow = workflow_module
