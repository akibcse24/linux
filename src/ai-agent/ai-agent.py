#!/usr/bin/env python3
import os
import sys
import re
import argparse
import subprocess

SYSTEM_PROMPT = """You are a system administrator and developer agent executing actions on a Debian Live OS (amd64).
You have full access to a local bash shell. You can execute shell commands by enclosing them in a markdown code block:
```bash
<command>
```
You can run any command, check files, run scripts, compile code, etc.
Only output one command block at a time. The agent loop will execute the command and return its stdout, stderr, and exit code.
Based on the results, you can execute further commands.
When the user's request is completely resolved, output "TASK_COMPLETE" along with a detailed explanation of the actions taken and the final output or state.
If you hit an error you cannot resolve, explain why and ask for guidance.
"""

class LLMSession:
    def send_message(self, message: str) -> str:
        raise NotImplementedError

class GeminiSession(LLMSession):
    def __init__(self, api_key: str):
        try:
            import google.generativeai as genai
        except ImportError:
            print("Error: 'google-generativeai' package is not installed.", file=sys.stderr)
            sys.exit(1)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT
        )
        self.chat = self.model.start_chat(history=[])

    def send_message(self, message: str) -> str:
        response = self.chat.send_message(message)
        return response.text

class OpenAISession(LLMSession):
    def __init__(self, api_key: str):
        try:
            from openai import OpenAI
        except ImportError:
            print("Error: 'openai' package is not installed.", file=sys.stderr)
            sys.exit(1)
        self.client = OpenAI(api_key=api_key)
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def send_message(self, message: str) -> str:
        self.messages.append({"role": "user", "content": message})
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=self.messages
        )
        reply = response.choices[0].message.content
        self.messages.append({"role": "assistant", "content": reply})
        return reply

class AnthropicSession(LLMSession):
    def __init__(self, api_key: str):
        try:
            from anthropic import Anthropic
        except ImportError:
            print("Error: 'anthropic' package is not installed.", file=sys.stderr)
            sys.exit(1)
        self.client = Anthropic(api_key=api_key)
        self.messages = []

    def send_message(self, message: str) -> str:
        self.messages.append({"role": "user", "content": message})
        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=self.messages
        )
        reply = response.content[0].text
        self.messages.append({"role": "assistant", "content": reply})
        return reply

def parse_bash_block(text: str) -> str | None:
    for block_type in ["bash", "sh", "shell"]:
        pattern = rf"```{block_type}\s*(.*?)\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None

def run_command(command: str) -> tuple[int, str, str]:
    print(f"\n[Agent] Executing command:\n--- COMMAND START ---\n{command}\n--- COMMAND END ---")
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")) + "\n[TimeoutExpired after 300s]"
        return -9, stdout, stderr
    except Exception as e:
        return -1, "", str(e)

def truncate_output(text: str, max_chars: int = 8000) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return f"{text[:half]}\n\n... [TRUNCATED {len(text) - max_chars} CHARACTERS] ...\n\n{text[-half:]}"

def main():
    parser = argparse.ArgumentParser(description="AI Agent Local Command Line Runner")
    parser.add_argument("prompt", type=str, help="Prompt or task for the AI agent")
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum execution steps")
    args = parser.parse_args()

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    session = None
    if gemini_key:
        print("[Agent] Initializing Gemini Provider")
        session = GeminiSession(gemini_key)
    elif openai_key:
        print("[Agent] Initializing OpenAI Provider")
        session = OpenAISession(openai_key)
    elif anthropic_key:
        print("[Agent] Initializing Anthropic Provider")
        session = AnthropicSession(anthropic_key)
    else:
        print("Error: No API key found in environment variables (GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY).", file=sys.stderr)
        sys.exit(1)

    next_message = args.prompt
    step = 0

    while step < args.max_steps:
        step += 1
        print(f"\n[Agent] Step {step}/{args.max_steps} - Sending request to LLM...")
        try:
            response_text = session.send_message(next_message)
        except Exception as e:
            print(f"Error communicating with LLM API: {e}", file=sys.stderr)
            sys.exit(2)

        print(f"\n[Agent] LLM Response:\n{response_text}")

        if "TASK_COMPLETE" in response_text:
            print("\n[Agent] Task successfully completed!")
            break

        command = parse_bash_block(response_text)
        if command:
            code, stdout, stderr = run_command(command)
            stdout_trunc = truncate_output(stdout)
            stderr_trunc = truncate_output(stderr)
            
            next_message = (
                f"Command exit code: {code}\n"
                f"Stdout:\n{stdout_trunc}\n"
                f"Stderr:\n{stderr_trunc}\n"
            )
        else:
            print("\n[Agent] No bash block found in response.")
            next_message = (
                "Please output either a bash command block starting with ```bash or output 'TASK_COMPLETE' if you are finished."
            )
    else:
        print("\n[Agent] Reached maximum steps without completion.", file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    main()
