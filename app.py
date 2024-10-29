from flask import Flask, request, jsonify
import io
import contextlib
import subprocess
import os
import signal
from flasgger import Swagger, swag_from

app = Flask(__name__)
swagger = Swagger(app)

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
            'description': 'No code provided',
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
    code = request.json.get('code', None)

    if code is None:
        return jsonify({'output': '', 'error': 'No code provided'}), 400

    # Capture stdout and stderr to a buffer
    stdout = io.StringIO()
    stderr = io.StringIO()
    output = ''
    error = ''

    try:
        # Use subprocess to run the code in a separate process
        proc = subprocess.Popen(
            ['python3', '-c', code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Use os.setsid to create a new session for the subprocess
        )

        # Allow the process to run for a limited time (10 seconds)
        try:
            output, error = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)  # Terminate the process group
            error = "Error: Code execution time limit exceeded."
            output = ''

        output = output.decode('utf-8')
        error = error.decode('utf-8')

    except Exception as e:
        output = ''
        error = f"Error: {str(e)}"

    return jsonify({'output': output, 'error': error})

if __name__ == '__main__':
    app.run(debug=True)
