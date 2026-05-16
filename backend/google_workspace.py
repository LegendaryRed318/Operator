import os
import os.path
import logging
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from paths import VAULT_PATH

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/presentations.readonly',
    'https://www.googleapis.com/auth/youtube.readonly'
]

TOKEN_PATH = VAULT_PATH / 'google_token.json'
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

class GoogleWorkspaceManager:
    def __init__(self):
        self.creds = None
        self.drive_service = None
        self.docs_service = None
        
    def _authenticate(self):
        """Authenticates with Google Workspace."""
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                # We need client_config for the flow.
                # If the user only provided CLIENT_ID, we might have trouble here.
                # We'll try to build a minimal config if they provide the secret later.
                client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
                if not client_secret:
                    logger.error("[Google] GOOGLE_CLIENT_SECRET not found in .env")
                    return False
                    
                client_config = {
                    "installed": {
                        "client_id": CLIENT_ID,
                        "project_id": "jarvis-operator",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_secret": client_secret,
                        "redirect_uris": ["http://localhost"]
                    }
                }
                
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                self.creds = flow.run_local_server(port=0)
                
            # Save the credentials for the next run
            with open(TOKEN_PATH, 'w') as token:
                token.write(self.creds.to_json())
        
        return True

    def get_drive_service(self):
        if not self.creds and not self._authenticate():
            return None
        if not self.drive_service:
            self.drive_service = build('drive', 'v3', credentials=self.creds)
        return self.drive_service

    def get_docs_service(self):
        if not self.creds and not self._authenticate():
            return None
        if not self.docs_service:
            self.docs_service = build('docs', 'v1', credentials=self.creds)
        return self.docs_service

    def list_recent_files(self, limit=10):
        """Lists the user's recent files from Google Drive."""
        service = self.get_drive_service()
        if not service: return "I'm unable to access your Google Drive, sir. Please check your credentials."
        
        try:
            results = service.files().list(
                pageSize=limit, 
                fields="nextPageToken, files(id, name, mimeType)",
                orderBy="modifiedTime desc"
            ).execute()
            items = results.get('files', [])

            if not items:
                return "No recent files found in your Google Drive, sir."
            
            output = "Here are your most recent Google Drive files:\n"
            for item in items:
                output += f"- {item['name']} ({item['mimeType'].split('.')[-1]})\n"
            return output
        except HttpError as error:
            logger.error(f"[Google] Drive API error: {error}")
            return f"I encountered an error accessing Google Drive: {error}"

    def read_doc_content(self, document_id):
        """Reads content from a Google Doc."""
        service = self.get_docs_service()
        if not service: return "I'm unable to access Google Docs, sir."
        
        try:
            doc = service.documents().get(documentId=document_id).execute()
            title = doc.get('title')
            content = ""
            for element in doc.get('body').get('content'):
                if 'paragraph' in element:
                    for part in element.get('paragraph').get('elements'):
                        if 'textRun' in part:
                            content += part.get('textRun').get('content')
            return f"Title: {title}\n\n{content}"
        except HttpError as error:
            logger.error(f"[Google] Docs API error: {error}")
            return f"I couldn't read the document: {error}"

_manager = None
def get_google_manager():
    global _manager
    if _manager is None:
        _manager = GoogleWorkspaceManager()
    return _manager
