import openai
import json

class OpenAIClient:
    def __init__(self, api_key):
        self.api_key = api_key
        openai.api_key = self.api_key

    def generate_code(self, description):
        try:
            prompt = self.generate_code_prompt(description)
            print(f"Prompt: {prompt}")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a code generator."},
                    {"role": "user", "content": prompt},
                ]
            )
            content = response["choices"][0]["message"]["content"]
            print(f"Response: {content}")
            formatted_response = self.parse_response(content)
            return formatted_response
        except Exception as e:
            print(f"Error with OpenAI API: {e}")
            return None

    def generate_code_prompt(self, description):
        """Generate a detailed and precise prompt for OpenAI."""
        return f"""
    You are a code generator. Based on the following description, generate Python code and its unit tests in the specified format.

    Description:
    {description}

    Requirements:
    1. Generate code for the application and write it to files named `<filename>.py`.
    2. For each code file, generate a corresponding test file named `test_<filename>.py` that includes unit tests.
    3. Ensure test files:
       - Import the code correctly using `from <filename> import <function/class>`.
       - Use `pytest` and include test cases following the `test_` naming convention.
       - Include a `pytest` fixture for setting up a Flask test client if the code is a Flask application.
    4. Provide setup instructions in a `README` file.

    Output format:
    ===========
    <filename>.py
    <code>
    ===========
    test_<filename>.py
    <unit tests>
    ===========
    README
    <setup instructions>

    Example for a Flask application:
    ===========
    app.py
    from flask import Flask

    app = Flask(__name__)

    @app.route('/')
    def hello():
        return 'Hello, World!'

    if __name__ == '__main__':
        app.run(host='0.0.0.0', port=8080)
    ===========
    test_app.py
    import pytest
    from app import app

    @pytest.fixture
    def client():
        with app.test_client() as client:
            yield client

    def test_hello(client):
        response = client.get('/')
        assert response.data == b'Hello, World!'
    ===========
    README
    1. Install dependencies: `pip install flask pytest`.
    2. Run the application: `python app.py`.
    3. Run tests: `pytest tests`.

    Begin the output now.
    """

    def parse_response(self, content):
        """
        Parse the response to extract code, unit tests, and setup instructions.
        Content is expected to have sections like:
        =========== app.py
        <code>
        =========== test_app.py
        <unit tests>
        =========== README
        <instructions>
        """
        files = []
        current_file = None
        current_content = []

        for line in content.splitlines():
            # Detect file sections marked with =========== <filename>
            if line.startswith("==========="):
                # Save the previous file (if any)
                if current_file:
                    files.append({"path": current_file, "content": self.clean_code_content("\n".join(current_content))})
                # Start a new file
                current_file = line.split("===========")[1].strip()
                current_content = []
            else:
                # Add line to the current file content
                if current_file:
                    current_content.append(line)

        # Save the last file
        if current_file:
            files.append({"path": current_file, "content": self.clean_code_content("\n".join(current_content))})

        return {"files": files}
    
    def clean_code_content(self, content):
        """
        Remove unnecessary language-specific notations (e.g., ```python, ```).
        """
        lines = content.splitlines()
        cleaned_lines = []
        for line in lines:
            # Ignore lines with backticks or language markers
            if not line.strip().startswith("```"):
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)
