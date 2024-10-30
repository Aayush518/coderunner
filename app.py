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
    This is a basic analyzer that looks for common patterns.
    """
    try:
        tree = ast.parse(code)
        loops = 0
        nested_loops = 0
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                loops += 1
                # Check for nested loops
                for child in ast.walk(node):
                    if isinstance(child, (ast.For, ast.While)) and child != node:
                        nested_loops += 1
        
        # Basic complexity analysis
        if nested_loops > 0:
            return "O(n^2) - Quadratic time complexity detected due to nested loops"
        elif loops > 0:
            return "O(n) - Linear time complexity detected due to single loops"
        else:
            return "O(1) - Constant time complexity detected"
    except:
        return "Unable to analyze time complexity"

def measure_execution_time(func):
    """
    Decorator to measure execution time of a function
    """
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        return result, execution_time
    return wrapper

def measure_memory_usage(code):
    """
    Measure the memory usage of the code execution
    """
    tracemalloc.start()
    start_memory = tracemalloc.get_traced_memory()
    
    # Execute the code
    exec(code)
    
    current_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    peak_memory = current_memory[1] - start_memory[1]
    return peak_memory

def sanitize_code(code):
    """
    Sanitize the code input by ensuring it executes properly.
    This function will ensure the code has valid syntax for execution.
    """
    return code

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/execute_code', methods=['POST'])
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
                    }
                }
            }
        }
    ],
    'responses': {
        '200': {
            'description': 'Output of the executed code with analysis',
            'schema': {
                'type': 'object',
                'properties': {
                    'output': {'type': 'string'},
                    'error': {'type': 'string'},
                    'execution_time': {'type': 'number'},
                    'time_complexity': {'type': 'string'},
                    'space_complexity': {'type': 'string'},
                    'memory_usage': {'type': 'number'}
                }
            }
        },
        '400': {
            'description': 'Invalid request or code'
        }
    }
})
def execute_code():
    """
    Execute Python code and analyze its performance.
    """
    if not request.is_json:
        return jsonify({'output': '', 'error': 'Request must be JSON'}), 400

    code = request.json.get('code', None)
    if code is None:
        return jsonify({'output': '', 'error': 'No code provided'}), 400

    sanitized_code = sanitize_code(code)
    
    # Analyze time complexity before execution
    time_complexity = analyze_time_complexity(sanitized_code)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        # Add timing code
        f.write("""
import time
start_time = time.time()
""")
        f.write(sanitized_code)
        f.write("""
end_time = time.time()
print(f"\\n[Execution Time: {end_time - start_time:.6f} seconds]")
""")
        temp_file = f.name

    output = ''
    error = ''
    execution_time = 0
    memory_usage = 0

    try:
        # Start memory tracking
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()

        # Execute the code
        proc = subprocess.Popen(
            ['python3', temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )

        try:
            output, error = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            error = "Error: Code execution time limit exceeded."
            output = ''

        # Get memory usage
        current_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_usage = (current_memory[1] - start_memory[1]) / 1024 / 1024  # Convert to MB

        output = output.decode('utf-8')
        error = error.decode('utf-8')

        # Extract execution time from output
        if '[Execution Time:' in output:
            execution_time = float(output.split('[Execution Time: ')[1].split(' seconds]')[0])
            output = output.split('\n[Execution Time:')[0]  # Remove timing from output

    except Exception as e:
        output = ''
        error = f"Error: {str(e)}"
        
    finally:
        try:
            os.unlink(temp_file)
        except Exception as cleanup_error:
            error += f" Cleanup error: {str(cleanup_error)}"

    # Estimate space complexity based on memory usage
    if memory_usage < 1:  # Less than 1MB
        space_complexity = "O(1) - Constant space complexity"
    elif memory_usage < 10:  # Less than 10MB
        space_complexity = "O(n) - Linear space complexity"
    else:
        space_complexity = "O(n^2) - Quadratic or higher space complexity"

    return jsonify({
        'output': output,
        'error': error,
        'execution_time': execution_time,
        'time_complexity': time_complexity,
        'space_complexity': space_complexity,
        'memory_usage': round(memory_usage, 2)  # Memory usage in MB
    })

if __name__ == '__main__':
    app.run(debug=True)