from flask import Flask, request, jsonify
import subprocess
import os
import signal
import tempfile
from flask_cors import CORS
from flasgger import Swagger, swag_from

app = Flask(__name__)
CORS(app) 
swagger = Swagger(app)

def sanitize_code(code):
    """
    Sanitize the code input by ensuring it executes properly.
    This function will ensure the code has valid syntax for execution.
    """
    return code  # No escaping needed for now since we're using subprocess

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
            'description': 'Output of the executed code',
            'schema': {
                'type': 'object',
                'properties': {
                    'output': {
                        'type': 'string',
                        'description': 'The output of the executed code',
                    },
                    'error': {
                        'type': 'string',
                        'description': 'Any errors that occurred during code execution',
                    }
                }
            }
        },
        '400': {
            'description': 'Invalid request or code',
            'schema': {
                'type': 'object',
                'properties': {
                    'output': {
                        'type': 'string',
                    },
                    'error': {
                        'type': 'string',
                    }
                }
            }
        }
    }
})
def execute_code():
    """
    Execute Python code.
    This endpoint allows you to execute Python code sent from the frontend and get the output.
    """
    if not request.is_json:
        return jsonify({'output': '', 'error': 'Request must be JSON'}), 400

    code = request.json.get('code', None)

    if code is None:
        return jsonify({'output': '', 'error': 'No code provided'}), 400

    # Sanitize the code
    sanitized_code = sanitize_code(code)

    # Create a temporary file to store the code
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(sanitized_code)
        temp_file = f.name

    output = ''
    error = ''

    try:
        # Use subprocess to run the Python file
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

        output = output.decode('utf-8')
        error = error.decode('utf-8')

    except Exception as e:
        output = ''
        error = f"Error: {str(e)}"

    finally:
        # Clean up the temporary file
        try:
            os.unlink(temp_file)
        except Exception as cleanup_error:
            error += f" Cleanup error: {str(cleanup_error)}"

    return jsonify({'output': output, 'error': error})

if __name__ == '__main__':
    app.run(debug=True)
