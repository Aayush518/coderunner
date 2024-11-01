from flask import Flask, request, jsonify
import subprocess
import os
import signal
import tempfile
import time
import sys
import ast
import tracemalloc
from flask_cors import CORS
from flask import render_template
from flasgger import Swagger, swag_from

app = Flask(__name__)
CORS(app)
swagger = Swagger(app)

def analyze_time_complexity(code):
    """
    Analyze the time complexity of the code by examining its structure.
    """
    try:
        tree = ast.parse(code)
        loops = 0
        nested_loops = 0
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                loops += 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.For, ast.While)) and child != node:
                        nested_loops += 1
        
        if nested_loops > 0:
            return "O(n^2) - Quadratic time complexity detected due to nested loops"
        elif loops > 0:
            return "O(n) - Linear time complexity detected due to single loops"
        else:
            return "O(1) - Constant time complexity detected"
    except:
        return "Unable to analyze time complexity"

def sanitize_code(code):
    """
    Sanitize the code input by ensuring it executes properly.
    """
    forbidden = ['os.system', 'subprocess', 'eval(', 'exec(', 'import os', 'import subprocess']
    code_lower = code.lower()
    for term in forbidden:
        if term.lower() in code_lower:
            raise ValueError(f"Forbidden code pattern detected: {term}")
    return code

def execute_single_run(code, single_input=None):
    """
    Execute code once with a single input value.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""
import time
import sys
from io import StringIO

class OutputCapture:
    def __init__(self):
        self.buffer = StringIO()
        self.input_mode = False
        
    def write(self, text):
        if not self.input_mode:
            self.buffer.write(text)
            
    def flush(self):
        self.buffer.flush()
    
    def mark_input(self):
        self.input_mode = True
    
    def unmark_input(self):
        self.input_mode = False
    
    def get_output(self):
        return self.buffer.getvalue()

class InputHandler:
    def __init__(self, input_value, output_capture):
        self.input_value = input_value
        self.output_capture = output_capture
        self.used = False
        
    def input(self, prompt=''):
        if prompt:
            self.output_capture.mark_input()
            sys.stdout.write(prompt)
            sys.stdout.flush()
            self.output_capture.unmark_input()
            
        if not self.used and self.input_value is not None:
            self.used = True
            return self.input_value
        return ''

# Setup output capture
output_capture = OutputCapture()
sys.stdout = output_capture

# Setup input handling
input_handler = InputHandler(""" + (repr(single_input) if single_input is not None else "None") + """, output_capture)
input = input_handler.input

try:
""")
        # Indent the user's code
        indented_code = '\n'.join('    ' + line for line in code.splitlines())
        f.write(indented_code)
        f.write("""

finally:
    # Get output
    final_output = output_capture.get_output()
    
    # Restore stdout
    sys.stdout = sys.__stdout__
    
    # Print output for parsing
    print("===OUTPUT_START===")
    print(final_output.rstrip())
    print("===OUTPUT_END===")
""")
        temp_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Extract output between markers
        output = ""
        if "===OUTPUT_START===" in result.stdout and "===OUTPUT_END===" in result.stdout:
            output = result.stdout.split("===OUTPUT_START===")[1].split("===OUTPUT_END===")[0].strip()
        
        return output
    finally:
        try:
            os.unlink(temp_file)
        except:
            pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/execute_code', methods=['POST'])
@swag_from({
    'tags': ['Code Execution'],
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'code': {
                        'type': 'string',
                        'description': 'The Python code to be executed',
                    },
                    'inputs': {
                        'type': 'string',
                        'description': 'Multi-line input string where each line is an input value'
                    }
                }
            }
        }
    ],
    'responses': {
        '200': {
            'description': 'Output of the executed code with analysis'
        }
    }
})
def execute_code():
    """
    Execute Python code multiple times, once for each input line.
    """
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    code = request.json.get('code', None)
    input_text = request.json.get('inputs', '')
    
    if code is None:
        return jsonify({'error': 'No code provided'}), 400

    try:
        sanitized_code = sanitize_code(code)
        time_complexity = analyze_time_complexity(sanitized_code)
        
        # Start memory and time tracking
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()
        start_time = time.time()
        
        # Handle empty input case
        if not input_text.strip():
            # Execute once with no input
            output = execute_single_run(sanitized_code, None)
            all_outputs = [output]
            inputs = []
        else:
            # Split input text into lines and filter out empty lines
            inputs = [line.strip() for line in input_text.split('\n') if line.strip()]
            # Execute code once for each input
            all_outputs = []
            for input_value in inputs:
                output = execute_single_run(sanitized_code, input_value)
                all_outputs.append(output)
        
        # Join all outputs with newlines
        final_output = '\n'.join(all_outputs)
        
        # Get memory usage and execution time
        current_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_usage = (current_memory[1] - start_memory[1]) / 1024 / 1024  # Convert to MB
        execution_time = time.time() - start_time

        return jsonify({
            'output': final_output,
            'error': '',
            'execution_time': execution_time,
            'time_complexity': time_complexity,
            'space_complexity': f"O(n) - Used {memory_usage:.2f}MB",
            'memory_usage': round(memory_usage, 2),
            'inputs_used': inputs
        })

    except Exception as e:
        return jsonify({
            'output': '',
            'error': f"Error: {str(e)}",
            'execution_time': 0,
            'time_complexity': time_complexity,
            'space_complexity': 'N/A',
            'memory_usage': 0,
            'inputs_used': []
        })

if __name__ == '__main__':
    app.run(debug=True)