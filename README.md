# Dropbox plugin

Lets Stavrobot browse, search, download and save files in your Dropbox.

## Before installing

You need your own Dropbox app, it's free and takes a couple of minutes:

1. Create one at https://www.dropbox.com/developers/apps with Scoped access. App folder limits the bot to `/Apps/<app name>`, Full Dropbox gives it everything.
2. On the Permissions tab enable `files.metadata.read`, `files.content.read`, `files.content.write`, `sharing.read` and `sharing.write`, then Submit. Do this before connecting, since a token only gets the scopes that were enabled when it was issued.

## Installation

Tell Stavrobot to install `https://github.com/vmasto/stavrobot-plugin-dropbox`.

## Configuration

- `app_key` and `app_secret`: from your app's Settings tab.
- `refresh_token`: leave it empty. Ask Stavrobot to connect Dropbox, it sends you a link, you allow access and paste back the code. The plugin saves the token itself.

## Tools

- `auth_url`, `auth_complete`: connect your account.
- `list_folder`: a folder's contents, optionally recursive.
- `search`: file names, and contents for documents Dropbox indexes.
- `get_metadata`: details for one file or folder.
- `download`: sends a file to the bot as an attachment, up to 25 MB.
- `upload`: saves an attachment or some text as a file, up to 25 MB. It won't overwrite unless asked, a clash gets a numbered name instead.
- `create_folder`, `move`, `copy`, `delete`.
- `get_link`: a shared link, or a direct download link that expires in 4 hours. Anyone with a shared link can open the file.

The 25 MB limit comes from Stavrobot's plugin runner, not Dropbox. You can turn off any tool, `delete` for example, on the plugins settings page.

## License

GNU Affero General Public License, version 3. See [LICENSE](LICENSE).
