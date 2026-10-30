"""Run existing approved W6 report engine on verified same-run Family data.

ChatGPT invokes this only when a member asks to generate a report. The W6
renderer is supplied by the trusted operator from the previously accepted
W6 v16 delivery; this module does not create another report template.
"""
from copy import deepcopy
from pathlib import Path
import importlib.util

SRC = Path(__file__).with_name("w6_current_data.py")


class MemberAnalysisReportProducer:
    """Inject an operator-verified native partial result into the existing API."""
    def __init__(self, request, result, *, source_id, rules_sha, sections=None,
                 approved_target=None,target_context=None,target_validator=None):
        self.request=deepcopy(request)
        self.result=deepcopy(result)
        self.source_id=source_id
        self.rules_sha=rules_sha
        self.sections=deepcopy(sections)
        self.approved_target=deepcopy(approved_target)
        self.target_context=deepcopy(target_context)
        self.target_validator=target_validator

    def __call__(self, formal_source, payload):
        spec=importlib.util.spec_from_file_location("family_w8_member_report_producer",
                                                  SRC.with_name("report_canonical_adapter.py"))
        adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        return adapter.make_member_review_inputs(formal_source,self.request,self.result,
            source_id=self.source_id,rules_sha=self.rules_sha,sections=self.sections,
            approved_target=self.approved_target,target_context=self.target_context,target_validator=self.target_validator)


class OnDemandW6Renderer:
    def __init__(self, trusted_current_input_producer, approved_w6_renderer=None,
                 *, approved_w6_archive=None):
        if not callable(trusted_current_input_producer):
            raise ValueError("W6_TRUSTED_PRODUCER_AND_APPROVED_RENDERER_REQUIRED")
        if approved_w6_archive is not None:
            if approved_w6_renderer is not None:
                raise ValueError("W6_RENDERER_SOURCE_CONFLICT")
            path = Path(__file__).with_name("w6_member_render.py")
            spec = importlib.util.spec_from_file_location("family_w8_member_renderer", path)
            if spec is None or spec.loader is None:
                raise RuntimeError("W6_APPROVED_RENDERER_NOT_FOUND")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # The renderer rechecks the approved v16 ZIP SHA before every job.
            archive = Path(approved_w6_archive)
            if not archive.is_file():
                raise ValueError("W6_APPROVED_ARCHIVE_REQUIRED")
            approved_w6_renderer = lambda current: module.render_current_w6(current, archive)
        if not callable(approved_w6_renderer):
            raise ValueError("W6_TRUSTED_PRODUCER_AND_APPROVED_RENDERER_REQUIRED")
        self.producer = trusted_current_input_producer
        self.renderer = approved_w6_renderer

    def __call__(self, formal_source, payload):
        if not isinstance(payload,dict) or set(payload) - {"date", "language"}:
            raise ValueError("W6_REPORT_OPTIONS_INVALID")
        if not isinstance(formal_source,dict) or formal_source.get("trade_authorization")!="NONE":
            raise ValueError("W6_FORMAL_SOURCE_REQUIRED")
        inputs=self.producer(deepcopy(formal_source),dict(payload))
        if (not isinstance(inputs,dict)
                or set(inputs)!={"market","engine"}
                or not isinstance(inputs["market"],dict)
                or not isinstance(inputs["engine"],dict)):
            raise ValueError("W6_CURRENT_INPUTS_MISSING")
        spec=importlib.util.spec_from_file_location("family_w8_w6_current_data", SRC)
        if spec is None or spec.loader is None:
            raise RuntimeError("W6_CURRENT_DATA_MODULE_MISSING")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        current=module.build_w6_current_data(formal_source,inputs["market"],inputs["engine"])
        # Approved W6 v16 renderer must use this payload, not its archived
        # Joseph report_data.json or old values embedded in demo content.
        output=self.renderer(deepcopy(current))
        if not isinstance(output,dict):
            raise ValueError("W6_RENDERER_RESULT_REQUIRED")
        if (output.get("qa_passed") is not True
                or output.get("renderer_contract")!="Family.W6.v16.parameterized"
                or output.get("client_id")!=current["client_id"]
                or output.get("source_db_sha256")!=current["source_db_sha256"]
                or output.get("source_digest")!=current["source_digest"]
                or output.get("w6_current_digest")!=current["digest"]
                or output.get("run_id")!=current["run_id"]
                or output.get("data_as_of")!=current["market_as_of"]
                or not isinstance(output.get("analysis_version"),str)
                or not output["analysis_version"].strip()):
            raise ValueError("W6_FORMAL_OUTPUT_QA_OR_SOURCE_MISMATCH")
        files=output.get("artifacts")
        if (not isinstance(files,dict) or not files
                or "report.pdf" not in files
                or "index.html" not in files):
            raise ValueError("W6_FORMAL_ARTIFACTS_INCOMPLETE")
        for name, data in files.items():
            if (not isinstance(name,str) or not name
                    or not isinstance(data,bytes) or not data
                    or len(data)>64*1024*1024):
                raise ValueError("W6_FORMAL_ARTIFACT_INVALID")
        return output
