import json

def debug_log():
    with open(r'C:\Users\asus\.gemini\antigravity\brain\b671b004-29cf-4579-b559-f19159c4a607\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
        with open('debug_log.txt', 'w', encoding='utf-8') as out:
            for line in f:
                if 'alpha_matte_refinement.py' in line and 'Showing lines' in line:
                    out.write(line + '\n\n')

if __name__ == "__main__":
    debug_log()
