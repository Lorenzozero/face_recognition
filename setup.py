#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open('README.md', encoding='utf-8') as f:
    readme = f.read()

requirements = [
    'insightface>=0.7.3',
    'numpy',
    'Pillow',
    'opencv-python-headless',
]

setup(
    name='face_recognition',
    version='2.0.0',
    description='Face recognition + OSINT — InsightFace backend, FastAPI server',
    long_description=readme,
    long_description_content_type='text/markdown',
    author='Lorenzozero',
    url='https://github.com/Lorenzozero/face_recognition',
    packages=find_packages(exclude=['tests*', 'examples*', 'docs*', 'dashboard*']),
    package_dir={},
    package_data={
        'face_recognition': ['backends/*.py'],
    },
    entry_points={
        'console_scripts': [
            'face_recognition=face_recognition.face_recognition_cli:main',
            'face_detection=face_recognition.face_detection_cli:main',
        ]
    },
    install_requires=requirements,
    license='MIT',
    zip_safe=False,
    python_requires='>=3.8',
    keywords='face_recognition insightface osint',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
