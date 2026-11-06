# Shared investigations with MongoDB

Collaborators connect directly from LinkDraw to the same MongoDB database.
There is no collaboration API server or separate hosting service. The app
polls MongoDB every two seconds and writes a new graph snapshot only when the
diagram changes. Revision checks detect simultaneous edits and prevent silent
overwrites.

## Requirements

- MongoDB Atlas or another MongoDB deployment reachable by every collaborator.
- A MongoDB database user with read/write access to the collaboration database.
- The same MongoDB connection URI and database name on each collaborator's
  computer.

For Atlas, add each collaborator's public IP to the project's Network Access
list. Atlas must accept connections from all collaborators' networks. Avoid
allowing `0.0.0.0/0` unless you understand and accept the additional exposure.
With a self-hosted database, configure firewall and TLS access appropriately.

## Connect in LinkDraw

Install dependencies:

```bash
python -m pip install -r req.txt
```

Open the diagram to share, then select **Collaboration → Connect / Create Shared
Investigation…**:

1. Enter the MongoDB connection URI. It is masked while being entered.
2. Enter the database name (for example, `linkdraw`).
3. Leave the investigation ID blank to create a shared copy of the current
   diagram. LinkDraw displays the generated ID.
4. On another computer, open LinkDraw and enter the same URI and database name,
   then enter the displayed ID to join. Confirm loading the shared diagram.

The shared data is stored in the `investigations` collection. Do not share a
MongoDB URI that grants access to unrelated databases. Create a dedicated
database user with the minimum permissions needed for this collection.

## Security trade-off

Direct database access means the MongoDB URI is entered into each collaborator's
app and used on that computer. Anyone who receives that URI can use its database
permissions outside LinkDraw too. The app does not save the URI to the project,
but direct MongoDB access cannot hide its credential from users who must connect.
If you need to avoid sharing database credentials, a trusted backend service is
necessary.

Use a TLS-enabled MongoDB connection (`mongodb+srv://` for Atlas). Do not put
the URI in source code or commit it to the repository. Rotate the database
password if it has been shared with someone who should no longer have access.

## Sync and conflicts

Changes are polled about every two seconds. If two people change the same
revision, the stale write is rejected and LinkDraw asks whether to load the
latest remote diagram, replace it with the local version, or disconnect while
keeping the local diagram. It does not silently merge changes.

Investigations are stored as MongoDB documents and must remain below MongoDB's
16 MB document limit. Image files referenced by local filesystem paths are not
uploaded; collaborators need access to those files on their own computers.
