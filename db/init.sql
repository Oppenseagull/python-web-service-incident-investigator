CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
INSERT INTO items (id, name) VALUES
    (1, 'Notebook'), (2, 'Pencil'), (3, 'Coffee')
ON CONFLICT (id) DO NOTHING;
