import os
import re
import subprocess
import json
from flask import Flask, request, jsonify, render_template_string
from api_clients.openai_client import OpenAIClient
import time
import requests
import sys


app = Flask(__name__)

WORKLOAD_DIRECTORY = "/home/nick/generated_workloads"
os.makedirs(WORKLOAD_DIRECTORY, exist_ok=True)

# Initialize API Client
api_client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))

HTML_FORM = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Submit Workload</title>
</head>
<body>
    <h1>Submit a Workload</h1>
    <form id="workloadForm">
        <label for="description">Workload Description:</label><br>
        <textarea id="description" name="description" rows="4" cols="50" required></textarea><br><br>
        <button type="button" onclick="submitWorkload()">Submit</button>
    </form>
    <p id="response"></p>
    
    <script>
        async function submitWorkload() {
            const description = document.getElementById('description').value;
            const responseElement = document.getElementById('response');
            responseElement.textContent = "Submitting...";

            const response = await fetch('/submit_workload', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ description }),
            });

            const result = await response.json();
            responseElement.textContent = JSON.stringify(result, null, 2);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    """Serve the HTML form for submitting a workload."""
    return render_template_string(HTML_FORM)
    
def summarize_test_results(test_results):
    """Summarize the test results for easier reporting."""
    summary = {"total": 0, "passed": 0, "failed": 0, "errors": []}
    
    for result in test_results:
        summary["total"] += 1
        if result.get("success", False):
            summary["passed"] += 1
        else:
            summary["failed"] += 1
            summary["errors"].append({
                "name": result.get("name", "Unknown Test"),
                "error": result.get("error", "No details available")
            })
    
    return summary


@app.route('/submit_workload', methods=['POST'])
def submit_workload():
    data = request.json
    workload_description = sanitize_input(data.get("description"))

    if not workload_description:
        return jsonify({"error": "No workload description provided"}), 400

    # Request code generation from the API client
    response = api_client.generate_code(workload_description)
    if not response:
        return jsonify({"error": "Failed to generate code"}), 500

    # Save generated files
    save_response_files(response["files"])

    # Extract test files from the response
    unit_tests = [file for file in response["files"] if file["path"].startswith("test_")]
    integration_tests = []  # Placeholder for future extension

    # Run tests
    test_results = run_tests(unit_tests, integration_tests)
    results_summary = summarize_test_results(test_results)

    return jsonify({
        "message": "Workload created and tested successfully.",
        "test_results": results_summary
    })

def sanitize_input(description):
    """Sanitize input to prevent injection attacks or invalid descriptions."""
    if not isinstance(description, str) or not description.strip():
        return None
    return re.sub(r'[^\w\s.,;?!()/-]', '', description)

def save_response_files(files):
    """Save files to the appropriate location in the workload directory."""
    for file in files:
        try:
            # Check if the file is a test file
            if file["path"].startswith("test_"):
                # Save test files directly to the tests directory
                test_dir = os.path.join(WORKLOAD_DIRECTORY, "tests")
                os.makedirs(test_dir, exist_ok=True)
                file_path = os.path.join(test_dir, file["path"])
            else:
                # Save non-test files to their specified paths
                file_path = os.path.join(WORKLOAD_DIRECTORY, file["path"])
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

            print(f"Saving file: {file_path}")  # Debug statement
            with open(file_path, "w") as f:
                f.write(file["content"])
                print(f"File saved: {file_path}")  # Debug statement
        except Exception as e:
            print(f"Error saving file {file_path}: {e}")

def parse_test_results(json_report_path):
    """Parse test results from the pytest JSON report."""
    results = []

    try:
        # Read the JSON report
        with open(json_report_path, "r") as f:
            report = json.load(f)
            for test in report.get("tests", []):
                results.append({
                    "name": test.get("nodeid"),
                    "success": test["outcome"] == "passed",
                    "error": test.get("call", {}).get("longrepr", "") if test["outcome"] != "passed" else None
                })
    except FileNotFoundError:
        print(f"Test report not found: {json_report_path}")
        results.append({
            "success": False,
            "error": "Test report not found."
        })
    except json.JSONDecodeError as e:
        print(f"Error parsing test report: {e}")
        results.append({
            "success": False,
            "error": "Error parsing test report."
        })

    return results



def run_tests(unit_tests, integration_tests=None):
    """Run unit tests and integration tests using pytest and capture JSON results."""
    results = []
    test_dir = os.path.join(WORKLOAD_DIRECTORY, "tests")
    app_dir = WORKLOAD_DIRECTORY  # Directory containing the application files
    os.makedirs(test_dir, exist_ok=True)

    # Save unit tests
    for test in unit_tests:
        test_file_path = os.path.join(test_dir, test["path"])
        with open(test_file_path, "w") as f:
            f.write(test["content"])

    # Debugging: Check test directory and files
    print(f"Running tests in: {test_dir}")
    print(f"Test files: {os.listdir(test_dir)}")
    print(f"App directory: {app_dir}")

    # Run pytest with the application directory added to PYTHONPATH
    try:
        result = subprocess.run(
            ["pytest", ".", "--json-report", "--json-report-file=test_report.json"],
            cwd=test_dir,  # Set working directory to tests directory
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": app_dir}  # Add app_dir to PYTHONPATH
        )
        print("Pytest output:", result.stdout)  # Debug pytest output
        print("Pytest error:", result.stderr)  # Debug pytest error

        # Check if test_report.json exists
        json_report_path = os.path.join(test_dir, "test_report.json")
        if not os.path.exists(json_report_path):
            print(f"JSON report not found: {json_report_path}")
            results.append({
                "success": False,
                "error": "Test report not found."
            })
            return results

        # Parse results if JSON report exists
        results = parse_test_results(json_report_path)
    except Exception as e:
        print(f"Error running tests: {e}")
        results.append({
            "success": False,
            "error": str(e)
        })

    return results

            
if __name__ == '__main__':
    app.run(debug=True)