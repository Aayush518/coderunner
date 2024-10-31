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
    Implement your security measures here.
    """
    forbidden = ['os.system', 'subprocess', 'eval(', 'exec(', 'import os', 'import subprocess']
    code_lower = code.lower()
    for term in forbidden:
        if term.lower() in code_lower:
            raise ValueError(f"Forbidden code pattern detected: {term}")
    return code

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
                        'type': 'array',
                        'items': {
                            'type': 'string'
                        },
                        'description': 'Array of input values for the program'
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
    Execute Python code with user inputs and analyze its performance.
    """
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    code = request.json.get('code', None)
    inputs = request.json.get('inputs', [])
    
    if code is None:
        return jsonify({'error': 'No code provided'}), 400

    try:
        sanitized_code = sanitize_code(code)
        time_complexity = analyze_time_complexity(sanitized_code)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
import time
import sys
from io import StringIO

class MultiOutputStream:
    def __init__(self):
        self.buffer = StringIO()
        self.stdout = sys.stdout
        
    def write(self, text):
        self.buffer.write(text)
        self.stdout.write(text)
        
    def flush(self):
        self.buffer.flush()
        self.stdout.flush()
        
    def getvalue(self):
        return self.buffer.getvalue()

class InputSimulator:
    def __init__(self, inputs):
        self.inputs = inputs
        self.input_index = 0
        self.inputs_used = []
        
    def input(self, prompt=''):
        if self.input_index < len(self.inputs):
            value = str(self.inputs[self.input_index])
            self.input_index += 1
            self.inputs_used.append(value)
            return value
        return ''

# Setup output and input handling
output_stream = MultiOutputStream()
sys.stdout = output_stream
input_simulator = InputSimulator(""" + str(inputs) + """)
input = input_simulator.input

# Start timing
start_time = time.time()

try:
""")
            # Indent the user's code
            indented_code = '\n'.join('    ' + line for line in sanitized_code.splitlines())
            f.write(indented_code)
            f.write("""

finally:
    # End timing
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Get results
    output = output_stream.getvalue()
    inputs_used = input_simulator.inputs_used

    # Restore stdout
    sys.stdout = sys.__stdout__

    # Print results in a format we can parse
    print("===EXECUTION_RESULTS===")
    print(f"TIME:{execution_time}")
    print(f"INPUTS_USED:{inputs_used}")
    print(f"OUTPUT:{output}")
""")
            temp_file = f.name

        try:
            # Start memory tracking
            tracemalloc.start()
            start_memory = tracemalloc.get_traced_memory()

            # Execute the code
            proc = subprocess.Popen(
                [sys.executable, temp_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )

            output, error = proc.communicate(timeout=10)

            # Get memory usage
            current_memory = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            memory_usage = (current_memory[1] - start_memory[1]) / 1024 / 1024  # Convert to MB

            # Parse the output
            output = output.decode('utf-8')
            error = error.decode('utf-8')

            execution_time = 0
            inputs_used = []
            final_output = ''

            # Extract execution details from output
            if "===EXECUTION_RESULTS===" in output:
                results_section = output.split("===EXECUTION_RESULTS===")[1]
                for line in results_section.split('\n'):
                    if line.startswith('TIME:'):
                        execution_time = float(line.split(':')[1])
                    elif line.startswith('INPUTS_USED:'):
                        inputs_used = eval(line.split(':')[1])
                    elif line.startswith('OUTPUT:'):
                        final_output = line.split('OUTPUT:', 1)[1].strip()

            return jsonify({
                'output': final_output,
                'error': error,
                'execution_time': execution_time,
                'time_complexity': time_complexity,
                'space_complexity': f"O(n) - Used {memory_usage:.2f}MB",
                'memory_usage': round(memory_usage, 2),
                'inputs_used': inputs_used
            })

        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            return jsonify({
                'error': 'Code execution timed out (10 second limit)',
                'output': '',
                'execution_time': 10,
                'time_complexity': time_complexity,
                'space_complexity': 'N/A',
                'memory_usage': 0,
                'inputs_used': []
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
        
    finally:
        try:
            os.unlink(temp_file)
        except:
            pass

if __name__ == '__main__':
    app.run(debug=True)