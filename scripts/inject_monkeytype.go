package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/syndtr/goleveldb/leveldb"
	"github.com/syndtr/goleveldb/leveldb/opt"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: inject_monkeytype \"your text here\"")
		fmt.Println("   or: inject_monkeytype --file text.txt")
		os.Exit(1)
	}

	text := strings.Join(os.Args[1:], " ")
	mode := "repeat"

	// Handle --file flag
	if len(os.Args) >= 3 && os.Args[1] == "--file" {
		data, err := os.ReadFile(os.Args[2])
		if err != nil {
			fmt.Printf("Error reading file: %v\n", err)
			os.Exit(1)
		}
		text = string(data)
	}

	words := strings.Fields(text)

	// Create the customTextSettings object
	customTextSettings := map[string]interface{}{
		"text":   words,
		"mode":   mode,
		"limit": map[string]interface{}{
			"value": len(words),
			"mode":  "word",
		},
		"pipeDelimiter": false,
	}

	// Convert to JSON
	jsonData, err := json.Marshal(customTextSettings)
	if err != nil {
		fmt.Printf("Error marshaling JSON: %v\n", err)
		os.Exit(1)
	}

	// Find Vivaldi's leveldb path
	homeDir, _ := os.UserHomeDir()
	possiblePaths := []string{
		filepath.Join(homeDir, ".config/vivaldi/Default/Local Storage/leveldb"),
		filepath.Join(homeDir, ".config/vivaldi/Default/Storage/ext/mpognobbkildjkofajifpdfhcoklimli/def/Local Storage/leveldb"),
	}

	var leveldbPath string
	for _, path := range possiblePaths {
		if _, err := os.Stat(filepath.Join(path, "CURRENT")); err == nil {
			leveldbPath = path
			break
		}
	}

	if leveldbPath == "" {
		fmt.Println("❌ Could not find Vivaldi's localStorage leveldb")
		fmt.Println("   Make sure Vivaldi is installed and has been run at least once")
		os.Exit(1)
	}

	fmt.Printf("📁 Found Vivaldi storage at: %s\n", leveldbPath)
	fmt.Printf("📝 Injecting text (%d words, %d chars)...\n", len(words), len(text))

	// Open leveldb
	db, err := leveldb.OpenFile(leveldbPath, &opt.Options{ReadOnly: false})
	if err != nil {
		fmt.Printf("❌ Error opening leveldb: %v\n", err)
		fmt.Println("\n💡 Make sure Vivaldi is CLOSED before running this!")
		os.Exit(1)
	}
	defer db.Close()

	// Key for customTextSettings in Chrome/Vivaldi localStorage
	key := []byte("_https://monkeytype.com\x00\x01customTextSettings")

	// Write the data
	if err := db.Put(key, jsonData); err != nil {
		fmt.Printf("❌ Error writing to database: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("✅ Successfully injected text into Vivaldi's localStorage!")
	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("✨ Next steps:")
	fmt.Println("   1. Open Vivaldi")
	fmt.Println("   2. Go to https://monkeytype.com")
	fmt.Println("   3. Your custom text should be active!")
	fmt.Println(strings.Repeat("=", 60))
}
