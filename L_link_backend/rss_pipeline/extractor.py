import os
import json
import logging
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Claude 클라이언트 초기화
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

V2_SCHEMA_PROMPT = """
You are an expert in knowledge graph extraction.
Extract nodes and edges from the provided news article based on the following v2 schema.
Respond strictly in JSON format. Do not include any other text or markdown wrapping.

Nodes:
- CentralAction (name, date, category)
- Program (name, program_type, status)
- LocalRegion (name, level)
- LocalAsset (name, asset_type)
- Stakeholder (name, stakeholder_type)
- LocalIssue (name, status)
- EcoIndicator (name, current_value)
- DataPoint (name, data_type)
- ReportingFrame (name, priority)
- NationalIssue (name)

Relationships (source_name, type, target_name, description):
- Type must be one of: OPERATES, RESPONDS_TO, LOCATED_IN, HAS_ISSUE, INVOLVES, AFFECTED_BY, MEASURES, INDICATES, REQUIRES_CHECK, SUGGESTS_FRAME, HAS_INTERVIEW_TARGET, LOCALIZED_TO, TARGETS, CONTRIBUTES_TO

Output format must be a JSON object matching this schema:
{
  "nodes": {
    "central_actions": [{"name": "", "date": "", "category": ""}],
    "programs": [{"name": "", "program_type": "", "status": ""}],
    "local_regions": [{"name": "", "level": ""}],
    "local_assets": [{"name": "", "asset_type": ""}],
    "stakeholders": [{"name": "", "stakeholder_type": ""}],
    "local_issues": [{"name": "", "status": ""}],
    "eco_indicators": [{"name": "", "current_value": ""}],
    "data_points": [{"name": "", "data_type": ""}],
    "reporting_frames": [{"name": "", "priority": ""}],
    "national_issues": [{"name": ""}]
  },
  "relationships": [
    {"source_name": "", "type": "", "target_name": "", "description": ""}
  ]
}

Make sure all node IDs are replaced by 'name'.
"""

def extract_knowledge_graph(text):
    if not text.strip():
        return None
        
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2048,
            temperature=0,
            system=V2_SCHEMA_PROMPT,
            messages=[
                {"role": "user", "content": f"Article Text:\n{text}"}
            ]
        )
        content = response.content[0].text
        # LLM이 markdown 코드로 감싸서 응답할 경우 정리
        if content.startswith("```json"):
            content = content.strip("```json").strip("```").strip()
        elif content.startswith("```"):
            content = content.strip("```").strip()
            
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Parse Error: {e} \nContent: {content}")
        return None
    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        return None
