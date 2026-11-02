"""Write local configuration examples, never edit the user's actual config."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
python = (root / '.venv/Scripts/python.exe').as_posix()
out = root / 'examples'
out.mkdir(exist_ok=True)
args = ['-m', 'qq_persona_agent.skill_export']
(out / 'codex-config.toml').write_text('[mcp_servers.qq_persona]\ncommand = ' + json.dumps(python, ensure_ascii=False) + '\nargs = ' + json.dumps(args) + '\nstartup_timeout_sec = 30\ntool_timeout_sec = 600\n', encoding='utf-8')
(out / '.mcp.json').write_text(json.dumps({'mcpServers': {'qq_persona': {'type': 'stdio', 'command': python, 'args': args}}}, ensure_ascii=False, indent=2), encoding='utf-8')
print('MCP config examples generated in examples/')
