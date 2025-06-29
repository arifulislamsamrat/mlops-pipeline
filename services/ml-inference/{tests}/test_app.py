import unittest
import json
from app import app

class TestMLInference(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_health_endpoint(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    def test_predict_endpoint(self):
        test_data = {'features': [1.0, 2.0, 3.0]}
        response = self.app.post('/predict',
                                data=json.dumps(test_data),
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('prediction', data)
        self.assertIn('model_version', data)

    def test_predict_no_features(self):
        response = self.app.post('/predict',
                                data=json.dumps({}),
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)

if __name__ == '__main__':
    unittest.main()
